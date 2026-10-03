# DeBank Scraper (Golang Port)

High-performance, resource-efficient Golang port of the DeBank portfolio scraper built using [`chromedp`](https://github.com/chromedp/chromedp) and optimized for **PRoot Debian (ARM64 / Termux)** environments.

---

## `chromedp` vs. `go-rod/rod` in PRoot Debian

When choosing between `chromedp` and `go-rod/rod` for a PRoot Debian environment (such as Termux PRoot on Android ARM64), **`chromedp` is the superior choice**. Here is why:

| Metric / Consideration | `chromedp` (Chosen) | `go-rod/rod` |
| :--- | :--- | :--- |
| **Syscall Overhead & PRoot Ptrace** | **Minimal**: Connects directly via WebSocket to Chrome's DevTools Protocol (CDP) port without intermediary process bridges. | **Heavier**: Uses higher-level abstraction loops, event multiplexers, and continuous polling goroutines that incur high `ptrace` context-switch overhead in PRoot. |
| **Browser Discovery & Auto-Download** | **Deterministic & Safe**: Uses existing local Chromium/Chrome installations (`CHROME_PATH`, Playwright cached Chromium, or Debian `/usr/bin/chromium`). Never attempts unexpected downloads. | **Hazardous on ARM64 PRoot**: Default launcher tries to auto-download Chromium from CDN, which frequently fails or downloads incompatible x86_64 binaries or glibc builds. |
| **PRoot Flag Customization** | **Direct & Explicit**: Seamlessly passes all required PRoot Chromium flags (`--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`, `--disable-software-rasterizer`, `--disable-setuid-sandbox`). | Requires custom `launcher.New()` configuration with stealth override hooks. |
| **Memory Footprint** | **~15–25 MB RSS** (compiled binary is only ~10MB). Crucial for mobile / PRoot memory limits. | **~60–100 MB RSS** due to internal element trees and DOM node tracking. |
| **DOM Evaluation Performance** | **Single CDP Roundtrip**: DeBank's rich client-rendered UI is extracted via a single in-page JavaScript evaluation (`chromedp.Evaluate`), avoiding multiple slow IPC calls over PRoot. | Supports JS evaluation, but with extra client-side wrapper layers. |

---

## Features

- **PRoot Debian ARM64 Ready**: Automatically configured with `--no-sandbox`, `--disable-dev-shm-usage`, and headless options required to run Chromium cleanly under PRoot.
- **Auto Browser Discovery**: Automatically checks:
  1. `$CHROME_PATH` / `$BROWSER_PATH`
  2. `/root/.cache/ms-playwright/chromium-1234/chrome-linux/chrome`
  3. `/usr/bin/chromium`, `/usr/bin/chromium-browser`, `/usr/bin/google-chrome`
- **Full Schema Compatibility**: Outputs JSON matching the exact schema expected by `portfolio-app` and `portfolio_integration.py` (`wallet`, `tokens`, `protocols`, `social`, `nfts`).
- **Flexible CLI & Library**: Can be invoked via command-line flags or imported directly as a Go package (`debank-scraper/pkg/scraper`).
- **Automatic .env Discovery**: Automatically traverses directories to find `.env` or `~/.secrets` for `ETH_ADDRESS` or `EVM_ADDRESS`.

---

## CLI Usage

### Build & Install

```bash
# Build binary
go build -o bin/debank-scrape main.go

# Install to $GOPATH/bin
go install ./cmd/debank-scrape
```

### Run Scraper

```bash
# Using ETH_ADDRESS from .env
debank-scrape --output ./data

# Specifying explicit address and target file
debank-scrape 0x1234567890abcdef1234567890abcdef12345678 -o ./data/custom_raw_debank.json

# Adjust timeout and browser path
debank-scrape --timeout 60000 --chrome-path /usr/bin/chromium -o ./data
```

### CLI Flags

| Flag | Default | Description |
| :--- | :--- | :--- |
| `[address]` | `$ETH_ADDRESS` or `$EVM_ADDRESS` | EVM wallet address to scrape |
| `-o`, `--output` | `$PORTFOLIO_DATA_DIR/<DATE>_raw_debank.json` | Destination folder or file path |
| `--timeout` | `45000` | Navigation & scrape timeout in milliseconds |
| `--chrome-path` | Auto-detected | Custom path to Chromium/Chrome executable |
| `--no-headless` | `false` | Run browser with visible GUI (if X11/Wayland display is available) |

---

## Go Package Usage

```go
package main

import (
	"context"
	"fmt"
	"time"

	"debank-scraper/pkg/scraper"
)

func main() {
	cfg := scraper.Config{
		Headless: true,
		Timeout:  45 * time.Second,
	}

	s := scraper.New(cfg)
	res, err := s.Scrape(context.Background(), "0xYourAddressHere")
	if err != nil {
		panic(err)
	}

	fmt.Printf("Total Net Worth: %s\n", *res.Wallet.TotalNetWorth)
	fmt.Printf("Found %d tokens, %d protocols\n", len(res.Tokens), len(res.Protocols))
}
```
