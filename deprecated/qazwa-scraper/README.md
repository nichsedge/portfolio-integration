# QAZWA Scraper

A Playwright-based scraper for QAZWA portfolio data.

## Installation

```bash
cd packages/qazwa-scraper
npm install
```

## Usage

1. Make sure your `.env` file has the following variables:
   ```env
   QAZWA_EMAIL=your_email@example.com
   QAZWA_PASSWORD=your_password
   ```

2. Run the scraper:
   ```bash
   npm run scrape
   ```

## Output

The scraper will:
- Open a browser window (headless: false) to perform the login
- Navigate to the portfolio page
- Extract portfolio data
- Save the data to `data/{date}_raw_qazwa.json`
- Capture screenshots to `data/screenshots/{date}/`

## Data Format

The output JSON contains:
- `timestamp`: ISO timestamp of the scrape
- `loginEmail`: The email used for login
- `portfolioUrl`: The portfolio page URL
- `basicData`: Basic portfolio information (summary, holdings, transactions)
- `detailedData`: Detailed portfolio information (accounts, assets, summary, metadata)
- `pageUrl`: Current page URL after login
- `pageTitle`: Page title

## Dependencies

- `playwright`: For browser automation
- `dotenv`: For environment variable management