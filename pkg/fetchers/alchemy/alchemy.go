package alchemy

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/nichsedge/portfolio-integration/pkg/models"
)

type TokenPrice struct {
	Currency string `json:"currency"`
	Value    string `json:"value"`
}

type TokenMetadata struct {
	Decimals int    `json:"decimals"`
	Name     string `json:"name"`
	Symbol   string `json:"symbol"`
}

type TokenRaw struct {
	Address       string        `json:"address"`
	Network       string        `json:"network"`
	TokenAddress  string        `json:"tokenAddress"`
	TokenBalance  string        `json:"tokenBalance"`
	TokenMetadata TokenMetadata `json:"tokenMetadata"`
	TokenPrices   []TokenPrice  `json:"tokenPrices"`
}

type AlchemyResponse struct {
	Data struct {
		Tokens []TokenRaw `json:"tokens"`
	} `json:"data"`
}

type AssetEntry struct {
	Address      string  `json:"address"`
	Network      string  `json:"network"`
	TokenAddress string  `json:"token_address"`
	Symbol       string  `json:"symbol"`
	Name         string  `json:"name"`
	Quantity     float64 `json:"quantity"`
	Decimals     int     `json:"decimals"`
	PriceUSD     float64 `json:"price_usd"`
	ValueUSD     float64 `json:"value_usd"`
}

type CuratedAlchemyData struct {
	Timestamp string       `json:"timestamp"`
	TotalUSD  float64      `json:"total_usd"`
	Assets    []AssetEntry `json:"assets"`
}

// Fetch queries the Alchemy API for Solana holdings.
func Fetch(apiKey, walletAddress string) (*CuratedAlchemyData, []models.Holding, error) {
	if apiKey == "" || walletAddress == "" {
		return nil, nil, fmt.Errorf("Alchemy API key or wallet address not provided")
	}

	url := fmt.Sprintf("https://api.g.alchemy.com/data/v1/%s/assets/tokens/by-address", apiKey)
	payload := map[string]interface{}{
		"addresses": []map[string]interface{}{
			{
				"address":  walletAddress,
				"networks": []string{"solana-mainnet"},
			},
		},
	}

	bodyBytes, _ := json.Marshal(payload)
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(bodyBytes))
	if err != nil {
		return nil, nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 20 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, nil, fmt.Errorf("Alchemy request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, nil, fmt.Errorf("Alchemy API returned status %d", resp.StatusCode)
	}

	var alchResp AlchemyResponse
	if err := json.NewDecoder(resp.Body).Decode(&alchResp); err != nil {
		return nil, nil, fmt.Errorf("failed to decode Alchemy response: %w", err)
	}

	curated := &CuratedAlchemyData{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Assets:    make([]AssetEntry, 0),
	}

	for _, t := range alchResp.Data.Tokens {
		// Convert hex balance to big.Int then float
		balanceInt := new(big.Int)
		hexStr := t.TokenBalance
		if len(hexStr) >= 2 && hexStr[:2] == "0x" {
			hexStr = hexStr[2:]
		}
		balanceInt.SetString(hexStr, 16)

		decimals := t.TokenMetadata.Decimals
		if decimals == 0 {
			decimals = 9
		}
		divisor := math.Pow(10, float64(decimals))
		fBalance, _ := new(big.Float).SetInt(balanceInt).Float64()
		qty := fBalance / divisor

		var priceUSD float64
		for _, p := range t.TokenPrices {
			if p.Currency == "usd" {
				var pv float64
				fmt.Sscanf(p.Value, "%f", &pv)
				priceUSD = pv
				break
			}
		}

		valUSD := qty * priceUSD
		symbol := t.TokenMetadata.Symbol
		if symbol == "" {
			symbol = "UNKNOWN"
		}
		name := t.TokenMetadata.Name
		if name == "" {
			name = symbol
		}

		curated.TotalUSD += valUSD
		curated.Assets = append(curated.Assets, AssetEntry{
			Address:      t.Address,
			Network:      t.Network,
			TokenAddress: t.TokenAddress,
			Symbol:       symbol,
			Name:         name,
			Quantity:     qty,
			Decimals:     decimals,
			PriceUSD:     priceUSD,
			ValueUSD:     valUSD,
		})
	}

	holdings := Standardize(curated)
	return curated, holdings, nil
}

// Standardize converts curated Alchemy data into standardized holdings.
func Standardize(data *CuratedAlchemyData) []models.Holding {
	var holdings []models.Holding
	usdThreshold := models.FilterThresholds["USD"]

	for _, a := range data.Assets {
		if a.ValueUSD < usdThreshold {
			continue
		}

		category := models.GetStandardCategory("Cryptocurrency", a.Symbol)
		price := a.PriceUSD
		valUSD := a.ValueUSD

		holdings = append(holdings, models.Holding{
			Source:     "SOL Wallet",
			Category:   category,
			Asset:      a.Symbol,
			Ticker:     a.Symbol,
			Name:       a.Name,
			Currency:   "USD",
			Quantity:   a.Quantity,
			Price:      &price,
			ValueUSD:   &valUSD,
			Account:    "Alchemy Wallet",
			Details:    fmt.Sprintf("Token: %s, Network: %s", a.Name, a.Network),
			AssetClass: models.GetAssetClass(category),
		})
	}

	return holdings
}

// SaveCurated dumps curated Alchemy data to disk.
func SaveCurated(data *CuratedAlchemyData, targetPath string) error {
	_ = os.MkdirAll(filepath.Dir(targetPath), 0755)
	b, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(targetPath, b, 0644)
}
