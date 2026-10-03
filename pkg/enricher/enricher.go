package enricher

import (
	"strings"

	"github.com/nichsedge/portfolio-integration/pkg/models"
)

// Official issuance coupon rates for Sovereign Sukuk & Retail Bonds (DJPPR)
var SBNRegistry = map[string]float64{
	"ST014T2": 0.0640, "ST014T4": 0.0650,
	"ST013T2": 0.0640, "ST013T4": 0.0650,
	"ST012T2": 0.0640, "ST012T4": 0.0655,
	"ST011T2": 0.0630, "ST011T4": 0.0650,
	"ST010T2": 0.0625, "ST010T4": 0.0640,
	"ST009":   0.0615, "ST008":   0.0580,
	"SR021T3": 0.0625, "SR021T5": 0.0645,
	"SR020T3": 0.0630, "SR020T5": 0.0640,
	"SR019T3": 0.0595, "SR019T5": 0.0610,
	"SR018T3": 0.0625, "SR018T5": 0.0640,
	"SR017":   0.0590, "SR016":   0.0495,
	"ORI026T3": 0.0630, "ORI026T6": 0.0640,
	"ORI025T3": 0.0625, "ORI025T6": 0.0640,
	"ORI024T3": 0.0610, "ORI024T6": 0.0635,
	"ORI023T3": 0.0590, "ORI023T6": 0.0610,
	"PBS003": 0.0600, "PBS032": 0.04875, "PBS036": 0.05375, "PBS038": 0.05875,
	"FR0070": 0.08375, "FR0081": 0.0650, "FR0096": 0.0700,
	"DX002ETCD0BN0101": 0.0625,
}

var CryptoStakingRates = map[string]float64{
	"SOL":  0.0680,
	"ETH":  0.0320,
	"DOT":  0.1150,
	"ATOM": 0.1350,
	"NEAR": 0.0750,
	"SUI":  0.0350,
	"ADA":  0.0280,
}

var BankCashRates = map[string]float64{
	"krom":      0.060,
	"seabank":   0.050,
	"superbank": 0.060,
	"jago":      0.035,
	"aladin":    0.050,
	"amar":      0.055,
}

const (
	DefaultP2PYield    = 0.1150
	DefaultSBNYield    = 0.0625
	DefaultMMFYield    = 0.0480
	DefaultDeFiYield   = 0.0750
	DefaultStakedYield = 0.0500
)

// EnrichHoldings populates yield_rate for all holdings based on asset class, category, and asset symbol.
func EnrichHoldings(holdings []models.Holding) []models.Holding {
	for i := range holdings {
		h := &holdings[i]
		if h.YieldRate != nil && *h.YieldRate > 0 {
			continue
		}

		assetUpper := strings.ToUpper(h.Asset)
		assetLower := strings.ToLower(h.Asset)
		cat := h.Category
		ac := h.AssetClass

		// 1. Sovereign Sukuk / Bonds
		if cat == "SBN" || cat == "Corporate Bond" || strings.Contains(cat, "Bond") || strings.Contains(assetUpper, "SUKUK") {
			rate := DefaultSBNYield
			for code, r := range SBNRegistry {
				if strings.Contains(assetUpper, code) {
					rate = r
					break
				}
			}
			h.YieldRate = &rate
			continue
		}

		// 2. P2P Lending
		if cat == "P2P Lending" || strings.Contains(cat, "P2P") {
			rate := DefaultP2PYield
			h.YieldRate = &rate
			continue
		}

		// 3. Crypto Staking / Yield
		if ac == "Crypto" {
			if cat == "Staked" || strings.Contains(cat, "Stak") {
				rate := DefaultStakedYield
				for coin, r := range CryptoStakingRates {
					if strings.Contains(assetUpper, coin) {
						rate = r
						break
					}
				}
				h.YieldRate = &rate
				continue
			}
			if cat == "Yield / LP" || strings.Contains(cat, "Yield") || strings.Contains(cat, "LP") {
				rate := DefaultDeFiYield
				h.YieldRate = &rate
				continue
			}
		}

		// 4. Money Market Fund
		if cat == "Money Market Fund" || strings.Contains(assetLower, "pasar uang") {
			rate := DefaultMMFYield
			h.YieldRate = &rate
			continue
		}

		// 5. Digital Banks / High-Yield Cash
		if ac == "Cash & Equivalents" {
			for bName, r := range BankCashRates {
				if strings.Contains(assetLower, bName) || strings.Contains(strings.ToLower(h.Account), bName) {
					rate := r
					h.YieldRate = &rate
					break
				}
			}
		}
	}
	return holdings
}
