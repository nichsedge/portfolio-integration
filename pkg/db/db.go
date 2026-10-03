package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/nichsedge/portfolio-integration/pkg/models"
	_ "modernc.org/sqlite"
)

const schema = `
CREATE TABLE IF NOT EXISTS snapshots (
    date TEXT PRIMARY KEY,
    net_worth_idr REAL NOT NULL,
    net_worth_usd REAL NOT NULL,
    total_assets_idr REAL NOT NULL,
    total_liabilities_idr REAL NOT NULL,
    investments_idr REAL NOT NULL,
    investments_usd REAL NOT NULL,
    bank_cash_idr REAL NOT NULL,
    bank_cash_usd REAL NOT NULL,
    exchange_rate REAL NOT NULL,
    total_items INTEGER NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    ticker TEXT,
    name TEXT,
    account TEXT,
    units REAL,
    price_idr REAL,
    value_idr REAL NOT NULL,
    value_usd REAL,
    allocation_pct REAL,
    yield_rate REAL,
    details TEXT,
    raw_json TEXT,
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS categories (
    snapshot_date TEXT NOT NULL,
    category TEXT NOT NULL,
    value_idr REAL NOT NULL,
    percentage REAL NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (snapshot_date, category),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_classes (
    snapshot_date TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    value_idr REAL NOT NULL,
    percentage REAL NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (snapshot_date, asset_class),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_states (
    snapshot_date TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    digest_md TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(date) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_holdings_date ON holdings(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_holdings_source ON holdings(source);
CREATE INDEX IF NOT EXISTS idx_holdings_category ON holdings(category);
`

// OpenDB opens a SQLite database at the given path with WAL mode.
func OpenDB(dbPath string) (*sql.DB, error) {
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, fmt.Errorf("failed to create db directory: %w", err)
	}

	dsn := fmt.Sprintf("%s?_pragma=journal_mode(WAL)&_pragma=foreign_keys(ON)", dbPath)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open sqlite database: %w", err)
	}

	if err := InitDB(db); err != nil {
		db.Close()
		return nil, err
	}

	return db, nil
}

// InitDB initializes database tables.
func InitDB(db *sql.DB) error {
	if _, err := db.Exec(schema); err != nil {
		return fmt.Errorf("failed to initialize schema: %w", err)
	}

	// Ensure yield_rate column exists
	rows, err := db.Query("PRAGMA table_info(holdings)")
	if err == nil {
		defer rows.Close()
		hasYield := false
		for rows.Next() {
			var cid int
			var name, ctype string
			var notnull, pk int
			var dfltValue interface{}
			if err := rows.Scan(&cid, &name, &ctype, &notnull, &dfltValue, &pk); err == nil {
				if name == "yield_rate" {
					hasYield = true
					break
				}
			}
		}
		if !hasYield {
			_, _ = db.Exec("ALTER TABLE holdings ADD COLUMN yield_rate REAL;")
		}
	}

	return nil
}

// UpsertSnapshot writes a full snapshot into SQLite.
func UpsertSnapshot(db *sql.DB, s *models.Snapshot) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	metaJSON, _ := json.Marshal(s.Metadata)
	createdAt := s.Metadata.GeneratedAt
	if createdAt == "" {
		createdAt = time.Now().UTC().Format(time.RFC3339)
	}

	// 1. Upsert snapshot
	querySnap := `
	INSERT INTO snapshots (
		date, net_worth_idr, net_worth_usd, total_assets_idr, total_liabilities_idr,
		investments_idr, investments_usd, bank_cash_idr, bank_cash_usd,
		exchange_rate, total_items, metadata_json, created_at
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	ON CONFLICT(date) DO UPDATE SET
		net_worth_idr=excluded.net_worth_idr,
		net_worth_usd=excluded.net_worth_usd,
		total_assets_idr=excluded.total_assets_idr,
		total_liabilities_idr=excluded.total_liabilities_idr,
		investments_idr=excluded.investments_idr,
		investments_usd=excluded.investments_usd,
		bank_cash_idr=excluded.bank_cash_idr,
		bank_cash_usd=excluded.bank_cash_usd,
		exchange_rate=excluded.exchange_rate,
		total_items=excluded.total_items,
		metadata_json=excluded.metadata_json,
		created_at=excluded.created_at;
	`
	_, err = tx.Exec(querySnap,
		s.Metadata.Date,
		s.Totals.NetWorthIDR,
		s.Totals.NetWorthUSD,
		s.Totals.TotalAssetsIDR,
		s.Totals.TotalLiabilitiesIDR,
		s.Totals.InvestmentsIDR,
		s.Totals.InvestmentsUSD,
		s.Totals.BankCashIDR,
		s.Totals.BankCashUSD,
		s.Metadata.ExchangeRate,
		s.Metadata.TotalItems,
		string(metaJSON),
		createdAt,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert snapshot: %w", err)
	}

	// 2. Clear existing child records for idempotency
	date := s.Metadata.Date
	if _, err := tx.Exec("DELETE FROM holdings WHERE snapshot_date = ?", date); err != nil {
		return err
	}
	if _, err := tx.Exec("DELETE FROM categories WHERE snapshot_date = ?", date); err != nil {
		return err
	}
	if _, err := tx.Exec("DELETE FROM asset_classes WHERE snapshot_date = ?", date); err != nil {
		return err
	}

	// 3. Insert categories
	for _, c := range s.Allocation.ByCategory {
		_, err := tx.Exec(
			"INSERT INTO categories (snapshot_date, category, value_idr, percentage, count) VALUES (?, ?, ?, ?, ?)",
			date, c.Category, c.ValueIDR, c.Percentage, c.Count,
		)
		if err != nil {
			return fmt.Errorf("failed to insert category: %w", err)
		}
	}

	// 4. Insert asset classes
	for _, ac := range s.Allocation.ByAssetClass {
		_, err := tx.Exec(
			"INSERT INTO asset_classes (snapshot_date, asset_class, value_idr, percentage, count) VALUES (?, ?, ?, ?, ?)",
			date, ac.AssetClass, ac.ValueIDR, ac.Percentage, ac.Count,
		)
		if err != nil {
			return fmt.Errorf("failed to insert asset class: %w", err)
		}
	}

	// 5. Insert holdings (use AllHoldings if present, fallback to Holdings)
	holdingsToInsert := s.AllHoldings
	if len(holdingsToInsert) == 0 {
		holdingsToInsert = s.Holdings
	}

	insertHoldingQuery := `
	INSERT INTO holdings (
		snapshot_date, source, category, asset_class, ticker, name,
		account, units, price_idr, value_idr, value_usd,
		allocation_pct, yield_rate, details, raw_json
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`

	stmt, err := tx.Prepare(insertHoldingQuery)
	if err != nil {
		return fmt.Errorf("failed to prepare holdings insert: %w", err)
	}
	defer stmt.Close()

	for _, h := range holdingsToInsert {
		rawJSON, _ := json.Marshal(h)
		name := h.Name
		if name == "" {
			name = h.Asset
		}
		if name == "" {
			name = h.Ticker
		}
		if name == "" {
			name = h.Account
		}

		var priceIDRVal *float64 = h.PriceIDR
		if priceIDRVal == nil {
			priceIDRVal = h.Price
		}

		var valIDR float64
		if h.ValueIDR != nil {
			valIDR = *h.ValueIDR
		}

		var valUSD *float64 = h.ValueUSD
		var allocPct *float64 = h.AllocationPercentage
		var yieldRate *float64 = h.YieldRate

		_, err := stmt.Exec(
			date,
			h.Source,
			h.Category,
			h.AssetClass,
			h.Ticker,
			name,
			h.Account,
			h.Quantity,
			priceIDRVal,
			valIDR,
			valUSD,
			allocPct,
			yieldRate,
			h.Details,
			string(rawJSON),
		)
		if err != nil {
			return fmt.Errorf("failed to insert holding %s: %w", name, err)
		}
	}

	return tx.Commit()
}
