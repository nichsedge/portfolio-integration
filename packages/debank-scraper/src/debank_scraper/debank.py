import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

def get_data_dir():
    repo_root = Path(__file__).resolve().parents[4]
    default_dir = repo_root / "data"
    data_dir_path = (
        os.getenv("PORTFOLIO_DATA_DIR")
        or os.getenv("DATA_DIR")
        or str(default_dir)
    )
    return Path(data_dir_path)

async def auto_scroll(page):
    await page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                let distance = 400;
                let timer = setInterval(() => {
                    let scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }
    """)

async def run():
    # Load env from root directory
    repo_root = Path(__file__).resolve().parents[4]
    root_env_path = repo_root / ".env"
    if root_env_path.exists():
        load_dotenv(dotenv_path=root_env_path)
    else:
        load_dotenv()

    evm_address = os.getenv("EVM_ADDRESS", "your_default_address_here")
    profile_url = f"https://debank.com/profile/{evm_address}"
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    data_dir = get_data_dir()
    
    # Ensure directory exists
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        print(f"Directory '{data_dir}' exists or was created.")
    except Exception as err:
        print(f"Failed to create directory: {err}", file=sys.stderr)
        
    output_path = data_dir / f"{current_date}_raw_debank.json"
    
    async with async_playwright() as p:
        print("Launching Chromium browser...")
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Log browser console messages
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))
        
        print(f"Navigating to {profile_url}...")
        await page.goto(profile_url, wait_until="load")
        
        try:
            # Wait for the main asset value to appear (using more robust selectors)
            await page.wait_for_selector(
                "div[class*='HeaderInfo_totalAssetInner'], div[class*='HeaderInfo_totalAsset'], div[class*='HeaderInfo_totalAssetValue']",
                timeout=30000
            )
        except Exception:
            print("Timed out waiting for total assets selector after 30s. Continuing...", file=sys.stderr)
            
        # Click 'Unfold chains' if present to get full breakdown
        try:
            unfold_btn = await page.query_selector("div[class*='AssetsOnChain_unfoldBtn']")
            if unfold_btn:
                print("Unfolding chains...")
                await unfold_btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            print("No unfold button found or failed to click.")
            
        # Scroll to load all lazy elements (tokens, protocols)
        print("Scrolling page to trigger lazy loading...")
        await auto_scroll(page)
        await page.wait_for_timeout(2000)
        
        # Evaluate page to scrape data
        print("Scraping page elements...")
        scraping_js = r"""
        () => {
            const data = {
              timestamp: new Date().toISOString(),
              wallet: {},
              social: {},
              tokens: [],
              protocols: [],
              nfts: []
            };

            // 1. Overview & Social
            const netWorthEl = document.querySelector("div[class*='HeaderInfo_totalAssetInner'], div[class*='HeaderInfo_totalAsset']");
            const changeEl = document.querySelector("div[class*='HeaderInfo_changePercent'], [class*='HeaderInfo_isLoss'], [class*='HeaderInfo_isProfit']");

            // Fallback if the specific value element is nested
            data.wallet.total_net_worth = netWorthEl ? (netWorthEl.querySelector("[class*='Value']")?.innerText.trim() || netWorthEl.innerText.split('\n')[0].trim()) : null;
            data.wallet.change_24h = changeEl ? changeEl.innerText.trim() : null;

            const rankingEl = document.querySelector("a[href='/ranking'][class*='RankingTag_rankingTag']");
            data.social.ranking = rankingEl ? rankingEl.innerText.trim() : null;

            const infoItems = document.querySelectorAll("div[class*='HeaderInfo_infoItem']");
            infoItems.forEach(item => {
              const text = item.innerText.trim();
              if (text.includes('Followers')) data.social.followers = text.replace('Followers', '').trim();
              else if (text.includes('Following')) data.social.following = text.replace('Following', '').trim();
              else if (text.includes('TVF')) data.social.tvf = text.replace('TVF', '').trim();
            });

            // 2. Wallet Tokens
            const tokenRows = document.querySelectorAll("div[class*='TokenWallet_table'] .db-table-row");
            tokenRows.forEach(row => {
              const symbol = row.querySelector("[class*='TokenWallet_detailLink']")?.innerText.trim();
              const cells = Array.from(row.querySelectorAll(".db-table-cell"));

              // Extract chain from the chain logo URL
              const chainLogoImg = row.querySelector("img[class*='TokenWallet_tokenChainIcon']");
              let chain = null;
              if (chainLogoImg && chainLogoImg.src) {
                const urlParts = chainLogoImg.src.split('/');
                const logoUrlIndex = urlParts.indexOf('logo_url');
                if (logoUrlIndex !== -1 && logoUrlIndex + 1 < urlParts.length) {
                  chain = urlParts[logoUrlIndex + 1];
                }
              }

              if (symbol && cells.length >= 4) {
                data.tokens.push({
                  symbol,
                  chain,
                  price: cells[1]?.innerText.trim(),
                  amount: cells[2]?.innerText.trim(),
                  value: cells[3]?.innerText.trim()
                });
              }
            });

            // 3. Protocols
            // Target full project sections for detail
            const protocolContainers = document.querySelectorAll("div[class*='Project_project__']");
            protocolContainers.forEach(container => {
              const nameEl = container.querySelector("[class*='ProjectTitle_projectTitle'], [class*='ProjectTitle_name'], [class*='Project_projectName']");
              const valueEl = container.querySelector("[class*='projectTitle-number'], [class*='ProjectTitle_number'], [class*='Project_projectValue']");
              
              if (nameEl) {
                let name = nameEl.innerText.trim().split('\n')[0].replace(/\$.*/, '').trim();
                const value = valueEl ? valueEl.innerText.trim() : null;
                
                const protocolData = {
                  name,
                  value,
                  positions: []
                };
                
                // Find position categories (e.g., Yield, Staked, Lending, Rewards)
                const categories = container.querySelectorAll("div[class*='Panel_container__']");
                categories.forEach(cat => {
                  const typeEl = cat.querySelector("div[class*='Panel_panelHead__']");
                  const type = typeEl ? typeEl.innerText.trim() : "Other";
                  
                  // Map headers to find Balance, Rewards, USD Value
                  const headers = Array.from(cat.querySelectorAll("div[class*='table_header__'] > div")).map(h => h.innerText.trim().toLowerCase());
                  const balanceIdx = headers.indexOf('balance');
                  const rewardsIdx = headers.indexOf('rewards');
                  const usdValueIdx = headers.lastIndexOf('usd value');

                  const rows = cat.querySelectorAll("div[class*='table_contentRow__']");
                  rows.forEach(row => {
                    const cells = Array.from(row.children);
                    if (cells.length >= 2) {
                      const poolName = cells[0].innerText.trim().replace(/\n/g, ' ');
                      const positionValue = usdValueIdx !== -1 && cells[usdValueIdx] ? cells[usdValueIdx].innerText.trim() : cells[cells.length - 1].innerText.trim();
                      
                      // Helper to get clean text from a cell
                      const getCleanedEntries = (cell) => {
                        if (!cell) return [];
                        const entries = [];
                        const tokenLinks = cell.querySelectorAll("a[class*='utils_detailLink__'], a[class*='TokenWallet_detailLink__']");
                        
                        if (tokenLinks.length === 0) {
                           const text = cell.innerText.trim().replace(/\n/g, ' ');
                           if (text) entries.push({ symbol: null, balance: text });
                        } else {
                          tokenLinks.forEach(link => {
                            const symbol = link.innerText.trim();
                            const cellClone = cell.cloneNode(true);
                            cellClone.querySelectorAll('button').forEach(btn => btn.remove());
                            let balanceText = cellClone.innerText.trim().replace(/\n/g, ' ');
                            balanceText = balanceText.replace(/\(\$.*?\)/g, '').trim();
                            entries.push({ symbol, balance: balanceText });
                          });
                        }
                        return entries;
                      };

                      const tokens = [];
                      if (balanceIdx !== -1) tokens.push(...getCleanedEntries(cells[balanceIdx]));
                      if (rewardsIdx !== -1) tokens.push(...getCleanedEntries(cells[rewardsIdx]));
                      
                      const uniqueTokens = [];
                      const seen = new Set();
                      tokens.forEach(t => {
                        const key = `${t.symbol}|${t.balance}`;
                        if (!seen.has(key)) {
                          uniqueTokens.push(t);
                          seen.add(key);
                        }
                      });

                      protocolData.positions.push({
                        type,
                        pool: poolName,
                        value: positionValue,
                        tokens: uniqueTokens
                      });
                    }
                  });
                });
                
                if (name && name !== 'Wallet' && !data.protocols.find(p => p.name === name)) {
                  data.protocols.push(protocolData);
                }
              }
            });

            // Fallback for summary-only items
            const summaryItems = document.querySelectorAll("[class*='ProjectCell_assetsItem'], [class*='ProjectCell_projectCell'], [class*='ProjectCell_assetsItemWrap']");
            summaryItems.forEach(item => {
              const nameEl = item.querySelector("[class*='ProjectCell_assetsItemNameText'], [class*='ProjectCell_name']");
              const valueEl = item.querySelector("[class*='ProjectCell_assetsItemWorth'], [class*='ProjectCell_value']");

              if (nameEl) {
                const name = nameEl.innerText.trim().split('\n')[0].replace(/\$.*/, '').trim();
                const value = valueEl ? valueEl.innerText.trim() : null;

                if (name && name !== 'Wallet' && !data.protocols.find(p => p.name === name)) {
                  data.protocols.push({ name, value, positions: [] });
                }
              }
            });

            return data;
        }
        """
        
        merged_data = await page.evaluate(scraping_js)
        
        # Save to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, indent=2)
            
        print(f"Data saved to {output_path}")
        await browser.close()

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
