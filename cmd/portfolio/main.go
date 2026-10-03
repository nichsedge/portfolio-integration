package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/joho/godotenv"
	"github.com/nichsedge/portfolio-integration/pkg/db"
	"github.com/nichsedge/portfolio-integration/pkg/fetchers/alchemy"
	"github.com/nichsedge/portfolio-integration/pkg/fetchers/binance"
	"github.com/nichsedge/portfolio-integration/pkg/fetchers/debank"
	"github.com/nichsedge/portfolio-integration/pkg/fetchers/ksei"
	"github.com/nichsedge/portfolio-integration/pkg/fetchers/sansfinance"
	"github.com/nichsedge/portfolio-integration/pkg/fx"
	"github.com/nichsedge/portfolio-integration/pkg/integrator"
	"github.com/nichsedge/portfolio-integration/pkg/models"
	"github.com/nichsedge/portfolio-integration/pkg/r2"
)

func loadEnv() {
	_ = godotenv.Load()
	home, err := os.UserHomeDir()
	if err == nil {
		_ = godotenv.Load(filepath.Join(home, ".secrets"))
		_ = godotenv.Load(filepath.Join(home, ".env"))
	}
	dir, err := os.Getwd()
	if err == nil {
		for i := 0; i < 5; i++ {
			envPath := filepath.Join(dir, ".env")
			if _, err := os.Stat(envPath); err == nil {
				_ = godotenv.Load(envPath)
				break
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
}

func dirExists(path string) bool {
	fi, err := os.Stat(path)
	return err == nil && fi.IsDir()
}

func getDataDir() string {
	d := os.Getenv("PORTFOLIO_DATA_DIR")
	if d == "" {
		d = os.Getenv("DATA_DIR")
	}
	if d != "" {
		home, err := os.UserHomeDir()
		if err == nil && strings.HasPrefix(d, "/home/al") && !dirExists(d) {
			d = filepath.Join(home, strings.TrimPrefix(d, "/home/al"))
		}
		return d
	}
	// Fallback to local data/
	dir, err := os.Getwd()
	if err == nil {
		localData := filepath.Join(dir, "data")
		if dirExists(localData) {
			return localData
		}
	}
	return "./data"
}

func main() {
	loadEnv()

	if len(os.Args) < 2 {
		printHelp()
		os.Exit(1)
	}

	command := os.Args[1]
	args := os.Args[2:]

	switch command {
	case "run-all":
		runAll(args)
	case "fetch":
		runFetch(args)
	case "integrate":
		runIntegrate(args)
	case "r2":
		runR2(args)
	case "help", "--help", "-h":
		printHelp()
	default:
		fmt.Printf("Unknown command: %s\n\n", command)
		printHelp()
		os.Exit(1)
	}
}

func printHelp() {
	fmt.Println("🚀 Portfolio Integration CLI (Go)")
	fmt.Println("\nUsage:")
	fmt.Println("  portfolio run-all       Run full multi-asset pipeline (fetch, integrate, persist, upload)")
	fmt.Println("  portfolio fetch <src>   Fetch single source (ksei, debank, binance, alchemy, sansfinance)")
	fmt.Println("  portfolio integrate     Integrate existing raw data into JSON snapshot and SQLite SSOT")
	fmt.Println("  portfolio r2 <action>   R2 cloud operations (push, status)")
}

func runAll(args []string) {
	fs := flag.NewFlagSet("run-all", flag.ExitOnError)
	dateFlag := fs.String("date", time.Now().Format("2006-01-02"), "Date in YYYY-MM-DD")
	noUpload := fs.Bool("no-upload", false, "Skip Cloudflare R2 backup")
	_ = fs.Parse(args)

	date := *dateFlag
	dataDir, _ := filepath.Abs(getDataDir())
	_ = os.MkdirAll(dataDir, 0755)

	fmt.Printf("🚀 Running full portfolio pipeline for %s\n", date)
	fmt.Printf("📁 Data directory: %s\n\n", dataDir)

	var allHoldings []models.Holding

	// 1. Fetch KSEI
	fmt.Print("⏳ [1/5] Fetching KSEI... ")
	kseiUser := os.Getenv("KSEI_USERNAME")
	if kseiUser == "" {
		kseiUser = os.Getenv("GOKSEI_USERNAME")
	}
	kseiPass := os.Getenv("KSEI_PASSWORD")
	if kseiPass == "" {
		kseiPass = os.Getenv("GOKSEI_PASSWORD")
	}
	plainPass := os.Getenv("KSEI_PLAIN_PASSWORD") != "false" && os.Getenv("GOKSEI_PLAIN_PASSWORD") != "false"

	rawKseiPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_ksei.json", date))
	if kseiUser != "" && kseiPass != "" {
		rawKsei, kseiHoldings, err := ksei.Fetch(kseiUser, kseiPass, plainPass)
		if err == nil {
			_ = ksei.SaveRaw(rawKsei, rawKseiPath)
			allHoldings = append(allHoldings, kseiHoldings...)
			fmt.Printf("✓ %d holdings\n", len(kseiHoldings))
		} else {
			fmt.Printf("⚠️ (%v) - checking cache fallback\n", err)
			tryFallbackCache(rawKseiPath, date, dataDir, "ksei")
		}
	} else {
		fmt.Println("⚠️ credentials missing - checking cache fallback")
		tryFallbackCache(rawKseiPath, date, dataDir, "ksei")
	}

	// 2. Fetch SansFinance
	fmt.Print("⏳ [2/5] Fetching SansFinance accounts from R2... ")
	r2Acc := os.Getenv("R2_ACCOUNT_ID")
	r2Key := os.Getenv("R2_ACCESS_KEY_ID")
	r2Sec := os.Getenv("R2_SECRET_ACCESS_KEY")
	r2Bucket := os.Getenv("R2_BUCKET_NAME")
	if r2Bucket == "" {
		r2Bucket = "ichsanul-dev"
	}

	rawSansPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_sansfinance.json", date))
	if r2Acc != "" && r2Key != "" && r2Sec != "" {
		rawSans, sansHoldings, err := sansfinance.Fetch(r2Acc, r2Key, r2Sec, r2Bucket)
		if err == nil {
			_ = sansfinance.SaveRaw(rawSans, rawSansPath)
			allHoldings = append(allHoldings, sansHoldings...)
			fmt.Printf("✓ %d accounts\n", len(sansHoldings))
		} else {
			fmt.Printf("⚠️ (%v) - checking cache fallback\n", err)
			tryFallbackCache(rawSansPath, date, dataDir, "sansfinance")
		}
	} else {
		fmt.Println("⚠️ credentials missing - checking cache fallback")
		tryFallbackCache(rawSansPath, date, dataDir, "sansfinance")
	}

	// 3. Fetch Alchemy (Solana)
	fmt.Print("⏳ [3/5] Fetching Solana assets (Alchemy)... ")
	solAddr := os.Getenv("SOL_ADDRESS")
	alchKey := os.Getenv("ALCHEMY_API_KEY")
	curatedAlchPath := filepath.Join(dataDir, fmt.Sprintf("%s_curated_alchemy.json", date))
	if solAddr != "" && alchKey != "" {
		curAlch, alchHoldings, err := alchemy.Fetch(alchKey, solAddr)
		if err == nil {
			_ = alchemy.SaveCurated(curAlch, curatedAlchPath)
			allHoldings = append(allHoldings, alchHoldings...)
			fmt.Printf("✓ %d tokens\n", len(alchHoldings))
		} else {
			fmt.Printf("⚠️ (%v) - checking cache fallback\n", err)
			tryFallbackCache(curatedAlchPath, date, dataDir, "alchemy")
		}
	} else {
		fmt.Println("⚠️ credentials missing - checking cache fallback")
		tryFallbackCache(curatedAlchPath, date, dataDir, "alchemy")
	}

	// 4. Fetch Binance
	fmt.Print("⏳ [4/5] Fetching Binance balances (Spot & Earn)... ")
	binKey := os.Getenv("BINANCE_API_KEY")
	binSec := os.Getenv("BINANCE_SECRET")
	rawBinPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_binance.json", date))
	if binKey != "" && binSec != "" {
		rawBin, binHoldings, err := binance.Fetch(binKey, binSec)
		if err == nil {
			_ = binance.SaveRaw(rawBin, rawBinPath)
			allHoldings = append(allHoldings, binHoldings...)
			fmt.Printf("✓ %d assets\n", len(binHoldings))
		} else {
			fmt.Printf("⚠️ (%v) - checking cache fallback\n", err)
			tryFallbackCache(rawBinPath, date, dataDir, "binance")
		}
	} else {
		fmt.Println("⚠️ credentials missing - checking cache fallback")
		tryFallbackCache(rawBinPath, date, dataDir, "binance")
	}

	// 5. Fetch DeBank (EVM)
	fmt.Print("⏳ [5/5] Fetching DeBank EVM balances... ")
	rawDebankPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_debank.json", date))
	evmAddr := os.Getenv("ETH_ADDRESS")
	if evmAddr == "" {
		evmAddr = os.Getenv("EVM_ADDRESS")
	}
	if evmAddr != "" {
		err := debank.Scrape(evmAddr, rawDebankPath)
		if err == nil {
			if _, dHoldings, err := debank.LoadRaw(rawDebankPath); err == nil {
				allHoldings = append(allHoldings, dHoldings...)
				fmt.Printf("✓ %d holdings\n", len(dHoldings))
			} else {
				fmt.Printf("⚠️ failed to parse: %v\n", err)
			}
		} else {
			fmt.Printf("⚠️ scrape failed (%v) - checking cache fallback\n", err)
			tryFallbackCache(rawDebankPath, date, dataDir, "debank")
			if _, dHoldings, err := debank.LoadRaw(rawDebankPath); err == nil {
				allHoldings = append(allHoldings, dHoldings...)
				fmt.Printf("✓ loaded %d cached holdings\n", len(dHoldings))
			}
		}
	} else {
		fmt.Println("⚠️ address missing - checking cache fallback")
		tryFallbackCache(rawDebankPath, date, dataDir, "debank")
		if _, dHoldings, err := debank.LoadRaw(rawDebankPath); err == nil {
			allHoldings = append(allHoldings, dHoldings...)
			fmt.Printf("✓ loaded %d cached holdings\n", len(dHoldings))
		}
	}

	// Step 6: Integration
	fmt.Println("\n--- Integrating Portfolio ---")
	rate := fx.GetExchangeRate(dataDir)
	fmt.Printf("💵 Exchange Rate: 1 USD = Rp %.2f\n", rate)

	dbPath := filepath.Join(dataDir, "portfolio.db")
	dbConn, err := db.OpenDB(dbPath)
	if err != nil {
		fmt.Printf("⚠️ Could not open SQLite DB (%v)\n", err)
	} else {
		defer dbConn.Close()
	}

	snap, err := integrator.Integrate(date, allHoldings, rate, dataDir, dbConn)
	if err != nil {
		fmt.Printf("❌ Integration failed: %v\n", err)
		os.Exit(1)
	}

	printSummary(snap)

	// Step 7: Cloud Upload
	if !*noUpload && r2Acc != "" && r2Key != "" && r2Sec != "" {
		fmt.Println("☁️ Uploading portfolio snapshot and DB to Cloudflare R2...")
		snapFile := filepath.Join(dataDir, fmt.Sprintf("%s_snapshot.json", date))
		latestFile := filepath.Join(dataDir, "latest_snapshot.json")

		_ = r2.UploadFile(r2Acc, r2Key, r2Sec, r2Bucket, snapFile, fmt.Sprintf("portfolio/%s_snapshot.json", date))
		_ = r2.UploadFile(r2Acc, r2Key, r2Sec, r2Bucket, latestFile, "portfolio/latest_snapshot.json")
		_ = r2.UploadFile(r2Acc, r2Key, r2Sec, r2Bucket, dbPath, "db/portfolio_latest.sqlite")
		fmt.Println("✓ Cloudflare R2 upload complete.")
	}

	fmt.Println("\n✨ Pipeline completed successfully!")
}

func tryFallbackCache(targetFile, today, dataDir, source string) {
	if _, err := os.Stat(targetFile); err == nil {
		return // already exists
	}
	pattern := filepath.Join(dataDir, fmt.Sprintf("*_raw_%s.json", source))
	if source == "alchemy" {
		pattern = filepath.Join(dataDir, fmt.Sprintf("*_curated_%s.json", source))
	}
	matches, _ := filepath.Glob(pattern)
	var latestMatch string
	for _, m := range matches {
		base := filepath.Base(m)
		if !strings.HasPrefix(base, today) && !strings.HasPrefix(base, "latest") {
			if m > latestMatch {
				latestMatch = m
			}
		}
	}
	if latestMatch != "" {
		content, err := os.ReadFile(latestMatch)
		if err == nil {
			_ = os.WriteFile(targetFile, content, 0644)
			fmt.Printf("  ↳ Reused cache from %s\n", filepath.Base(latestMatch))
		}
	}
}

func printSummary(snap *models.Snapshot) {
	fmt.Println("\n=======================================================")
	fmt.Printf("📊 PORTFOLIO SNAPSHOT: %s\n", snap.Metadata.Date)
	fmt.Printf("💰 Net Worth:    Rp %s ($%.2f)\n", formatIDR(snap.Totals.NetWorthIDR), snap.Totals.NetWorthUSD)
	fmt.Printf("   Assets:       Rp %s\n", formatIDR(snap.Totals.TotalAssetsIDR))
	if snap.Totals.TotalLiabilitiesIDR > 0 {
		fmt.Printf("   Liabilities:  Rp %s\n", formatIDR(snap.Totals.TotalLiabilitiesIDR))
	}
	fmt.Printf("   Investments:  Rp %s ($%.2f)\n", formatIDR(snap.Totals.InvestmentsIDR), snap.Totals.InvestmentsUSD)
	fmt.Printf("   Liquid Cash:  Rp %s ($%.2f)\n", formatIDR(snap.Totals.BankCashIDR), snap.Totals.BankCashUSD)
	fmt.Println("-------------------------------------------------------")
	fmt.Println("Asset Allocation:")
	for _, ac := range snap.Allocation.ByAssetClass {
		fmt.Printf("  %-20s  Rp %-14s  (%5.1f%%)  [%d]\n", ac.AssetClass, formatIDR(ac.ValueIDR), ac.Percentage, ac.Count)
	}
	fmt.Println("=======================================================\n")
}

func formatIDR(v float64) string {
	s := fmt.Sprintf("%.0f", v)
	var parts []string
	for len(s) > 3 {
		parts = append([]string{s[len(s)-3:]}, parts...)
		s = s[:len(s)-3]
	}
	if len(s) > 0 {
		parts = append([]string{s}, parts...)
	}
	return strings.Join(parts, ",")
}

func runFetch(args []string) {
	if len(args) == 0 {
		fmt.Println("Please specify source: ksei, debank, binance, alchemy, sansfinance")
		os.Exit(1)
	}
	dataDir, _ := filepath.Abs(getDataDir())
	date := time.Now().Format("2006-01-02")

	switch args[0] {
	case "ksei":
		user := os.Getenv("KSEI_USERNAME")
		pass := os.Getenv("KSEI_PASSWORD")
		raw, _, err := ksei.Fetch(user, pass, true)
		if err != nil {
			fmt.Printf("Error: %v\n", err)
			os.Exit(1)
		}
		target := filepath.Join(dataDir, fmt.Sprintf("%s_raw_ksei.json", date))
		_ = ksei.SaveRaw(raw, target)
		fmt.Printf("✓ Saved to %s\n", target)
	case "sansfinance":
		r2Acc := os.Getenv("R2_ACCOUNT_ID")
		r2Key := os.Getenv("R2_ACCESS_KEY_ID")
		r2Sec := os.Getenv("R2_SECRET_ACCESS_KEY")
		raw, _, err := sansfinance.Fetch(r2Acc, r2Key, r2Sec, "ichsanul-dev")
		if err != nil {
			fmt.Printf("Error: %v\n", err)
			os.Exit(1)
		}
		target := filepath.Join(dataDir, fmt.Sprintf("%s_raw_sansfinance.json", date))
		_ = sansfinance.SaveRaw(raw, target)
		fmt.Printf("✓ Saved to %s\n", target)
	default:
		fmt.Printf("Fetch for %s not implemented or run via run-all\n", args[0])
	}
}

func runIntegrate(args []string) {
	fs := flag.NewFlagSet("integrate", flag.ExitOnError)
	dateFlag := fs.String("date", time.Now().Format("2006-01-02"), "Date in YYYY-MM-DD")
	_ = fs.Parse(args)

	date := *dateFlag
	dataDir, _ := filepath.Abs(getDataDir())
	rate := fx.GetExchangeRate(dataDir)

	var allHoldings []models.Holding

	// Load existing raw files
	kseiPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_ksei.json", date))
	if raw, err := os.ReadFile(kseiPath); err == nil {
		var d ksei.RawKseiData
		if json.Unmarshal(raw, &d) == nil {
			allHoldings = append(allHoldings, ksei.Standardize(&d)...)
		}
	}

	debankPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_debank.json", date))
	if _, h, err := debank.LoadRaw(debankPath); err == nil {
		allHoldings = append(allHoldings, h...)
	}

	binPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_binance.json", date))
	if raw, err := os.ReadFile(binPath); err == nil {
		var d binance.RawBinanceData
		if json.Unmarshal(raw, &d) == nil {
			allHoldings = append(allHoldings, binance.Standardize(&d)...)
		}
	}

	alchPath := filepath.Join(dataDir, fmt.Sprintf("%s_curated_alchemy.json", date))
	if raw, err := os.ReadFile(alchPath); err == nil {
		var d alchemy.CuratedAlchemyData
		if json.Unmarshal(raw, &d) == nil {
			allHoldings = append(allHoldings, alchemy.Standardize(&d)...)
		}
	}

	sansPath := filepath.Join(dataDir, fmt.Sprintf("%s_raw_sansfinance.json", date))
	if raw, err := os.ReadFile(sansPath); err == nil {
		var d sansfinance.RawSansfinanceData
		if json.Unmarshal(raw, &d) == nil {
			allHoldings = append(allHoldings, sansfinance.Standardize(&d)...)
		}
	}

	dbPath := filepath.Join(dataDir, "portfolio.db")
	dbConn, _ := db.OpenDB(dbPath)
	if dbConn != nil {
		defer dbConn.Close()
	}

	snap, err := integrator.Integrate(date, allHoldings, rate, dataDir, dbConn)
	if err != nil {
		fmt.Printf("❌ Integration failed: %v\n", err)
		os.Exit(1)
	}

	printSummary(snap)
}

func runR2(args []string) {
	if len(args) == 0 {
		fmt.Println("Usage: portfolio r2 [push|status]")
		return
	}
	switch args[0] {
	case "push":
		dataDir, _ := filepath.Abs(getDataDir())
		dbPath := filepath.Join(dataDir, "portfolio.db")
		r2Acc := os.Getenv("R2_ACCOUNT_ID")
		r2Key := os.Getenv("R2_ACCESS_KEY_ID")
		r2Sec := os.Getenv("R2_SECRET_ACCESS_KEY")
		r2Bucket := os.Getenv("R2_BUCKET_NAME")
		if r2Bucket == "" {
			r2Bucket = "ichsanul-dev"
		}
		if err := r2.UploadFile(r2Acc, r2Key, r2Sec, r2Bucket, dbPath, "db/portfolio_latest.sqlite"); err != nil {
			fmt.Printf("❌ Failed to upload DB: %v\n", err)
		} else {
			fmt.Println("✓ Uploaded db/portfolio_latest.sqlite to Cloudflare R2")
		}
	case "status":
		fmt.Println("Cloudflare R2 bucket: ichsanul-dev")
	}
}
