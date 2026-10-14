package alchemy

import (
	"testing"
)

func TestStandardize(t *testing.T) {
	curated := &CuratedAlchemyData{
		Timestamp: "2026-10-14T00:00:00Z",
		Assets: []AssetEntry{
			{Symbol: "SOL", Name: "Solana", Network: "solana", Quantity: 5.0, PriceUSD: 150.0, ValueUSD: 750.0},
			{Symbol: "USDC", Name: "USD Coin", Network: "solana", Quantity: 200.0, PriceUSD: 1.0, ValueUSD: 200.0},
			{Symbol: "MEME", Name: "Meme Token", Network: "solana", Quantity: 1000.0, PriceUSD: 0.001, ValueUSD: 1.0}, // < $5 dust
		},
	}

	holdings := Standardize(curated)
	if len(holdings) != 2 {
		t.Fatalf("expected 2 holdings after dust filter, got %d", len(holdings))
	}

	for _, h := range holdings {
		if h.Source != "alchemy" {
			t.Errorf("expected source alchemy, got %s", h.Source)
		}
		switch h.Asset {
		case "SOL":
			if h.Category != "Spot" || h.AssetClass != "Crypto" {
				t.Errorf("unexpected SOL classification: cat=%s, ac=%s", h.Category, h.AssetClass)
			}
			if *h.ValueUSD != 750.0 {
				t.Errorf("unexpected SOL value: %f", *h.ValueUSD)
			}
		case "USDC":
			if h.Category != "Stablecoin" || h.AssetClass != "Cash & Equivalents" {
				t.Errorf("unexpected USDC classification: cat=%s, ac=%s", h.Category, h.AssetClass)
			}
			if *h.ValueUSD != 200.0 {
				t.Errorf("unexpected USDC value: %f", *h.ValueUSD)
			}
		default:
			t.Errorf("unexpected asset: %s", h.Asset)
		}
	}
}
