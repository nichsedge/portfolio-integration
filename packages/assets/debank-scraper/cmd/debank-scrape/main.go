package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"debank-scraper/pkg/scraper"
	"github.com/joho/godotenv"
)

func loadEnv() {
	// 1. Try local directory .env
	_ = godotenv.Load()

	// 2. Try root repo .env by walking up to find .git or packages
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

	// 3. Fallback to ~/.secrets if present
	home, err := os.UserHomeDir()
	if err == nil {
		secretsPath := filepath.Join(home, ".secrets")
		if _, err := os.Stat(secretsPath); err == nil {
			_ = godotenv.Load(secretsPath)
		}
	}
}

func resolveOutputPath(outputTarget string) (string, error) {
	currentDate := time.Now().Format("2006-01-02")
	fileName := fmt.Sprintf("%s_raw_debank.json", currentDate)

	if outputTarget == "" {
		dataDir := os.Getenv("PORTFOLIO_DATA_DIR")
		if dataDir == "" {
			dataDir = os.Getenv("DATA_DIR")
		}
		if dataDir == "" {
			dataDir = "./data"
		}
		dataDir = strings.Trim(strings.TrimSpace(dataDir), `"'`)
		absDir, err := filepath.Abs(dataDir)
		if err != nil {
			return "", err
		}
		return filepath.Join(absDir, fileName), nil
	}

	cleanTarget := strings.Trim(strings.TrimSpace(outputTarget), `"'`)
	absTarget, err := filepath.Abs(cleanTarget)
	if err != nil {
		return "", err
	}

	// Check if target is intended as directory
	fi, err := os.Stat(absTarget)
	if (err == nil && fi.IsDir()) || strings.HasSuffix(cleanTarget, "/") || filepath.Ext(cleanTarget) == "" {
		return filepath.Join(absTarget, fileName), nil
	}

	return absTarget, nil
}

func main() {
	loadEnv()

	var (
		outputFlag     string
		noHeadlessFlag bool
		timeoutMsFlag  int
		chromePathFlag string
	)

	flag.StringVar(&outputFlag, "o", "", "Output directory or file path for the scraped JSON")
	flag.StringVar(&outputFlag, "output", "", "Output directory or file path for the scraped JSON")
	flag.BoolVar(&noHeadlessFlag, "no-headless", false, "Run browser in non-headless (visible) mode")
	flag.IntVar(&timeoutMsFlag, "timeout", 45000, "Page load timeout in milliseconds")
	flag.StringVar(&chromePathFlag, "chrome-path", "", "Custom path to Chromium/Chrome executable")

	flag.Parse()

	// Extract address: positional arg or env var
	var address string
	if flag.NArg() > 0 {
		address = flag.Arg(0)
	}
	if address == "" {
		address = os.Getenv("ETH_ADDRESS")
	}
	if address == "" {
		address = os.Getenv("EVM_ADDRESS")
	}

	address = scraper.CleanAddress(address)
	if address == "" || address == "your_default_address_here" {
		fmt.Fprintln(os.Stderr, "❌ Error: EVM wallet address must be provided as an argument or via ETH_ADDRESS/EVM_ADDRESS env var.")
		os.Exit(1)
	}

	outputPath, err := resolveOutputPath(outputFlag)
	if err != nil {
		log.Fatalf("❌ Error resolving output path: %v", err)
	}

	cfg := scraper.Config{
		Headless:   !noHeadlessFlag,
		Timeout:    time.Duration(timeoutMsFlag) * time.Millisecond,
		ChromePath: chromePathFlag,
	}

	s := scraper.New(cfg)
	ctx := context.Background()

	fmt.Fprintf(os.Stderr, "Scraping DeBank for wallet: %s...\n", address)
	result, err := s.ScrapeToFile(ctx, address, outputPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ Error scraping DeBank: %v\n", err)
		os.Exit(1)
	}

	netWorth := "N/A"
	if result.Wallet.TotalNetWorth != nil {
		netWorth = *result.Wallet.TotalNetWorth
	}

	tokensCount := len(result.Tokens)
	protocolsCount := len(result.Protocols)

	fmt.Fprintf(os.Stderr, "✓ Successfully scraped %d tokens and %d protocols (Net Worth: %s)\n", tokensCount, protocolsCount, netWorth)
	fmt.Fprintf(os.Stderr, "✓ Saved to: %s\n", outputPath)
}
