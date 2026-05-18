import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';

import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootEnvPath = path.resolve(__dirname, '../../.env');

if (existsSync(rootEnvPath)) {
  dotenv.config({ path: rootEnvPath });
} else {
  dotenv.config();
}

const EVM_ADDRESS = process.env.EVM_ADDRESS || "your_default_address_here";

const PROFILE_URL = `https://debank.com/profile/${EVM_ADDRESS}`;

const getCurrentDate = () => {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getDataDir = () => {
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const repoRoot = path.resolve(scriptDir, '../../');
  return process.env.PORTFOLIO_DATA_DIR || process.env.DATA_DIR || path.join(repoRoot, 'data');
};

const currentDate = getCurrentDate();
const dataDir = getDataDir();
const OUTPUT_PATH = path.join(dataDir, `${currentDate}_raw_debank.json`);
const dirname = path.dirname(OUTPUT_PATH);

async function ensureDirectoryExists() {
  try {
    await fs.mkdir(dirname, { recursive: true });
    console.log(`Directory '${dirname}' exists or was created.`);
  } catch (err) {
    console.error(`Failed to create directory:`, err);
  }
}
ensureDirectoryExists();

async function autoScroll(page) {
  await page.evaluate(async () => {
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
  });
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();

  // Log browser console messages
  page.on('console', msg => console.log('BROWSER LOG:', msg.text()));

  console.log(`Navigating to ${PROFILE_URL}...`);
  await page.goto(PROFILE_URL, { waitUntil: "load" });

  try {
    // Wait for the main asset value to appear (using more robust selectors)
    await page.waitForSelector("div[class*='HeaderInfo_totalAssetInner'], div[class*='HeaderInfo_totalAsset'], div[class*='HeaderInfo_totalAssetValue']", { timeout: 30000 });
  } catch (e) {
    console.warn("Timed out waiting for total assets selector after 30s. Continuing...");
  }

  // Click 'Unfold chains' if present to get full breakdown
  try {
    const unfoldBtn = await page.$("div[class*='AssetsOnChain_unfoldBtn']");
    if (unfoldBtn) {
      console.log("Unfolding chains...");
      await unfoldBtn.click();
      await page.waitForTimeout(1000);
    }
  } catch (e) {
    console.log("No unfold button found or failed to click.");
  }

  // Scroll to load all lazy elements (tokens, protocols)
  await autoScroll(page);
  await page.waitForTimeout(2000);

  const mergedData = await page.evaluate(() => {
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
  });

  // 4. NFTs
  // console.log("Navigating to NFT tab...");
  // const NFT_URL = `${PROFILE_URL}/nft`;
  // await page.goto(NFT_URL, { waitUntil: "networkidle" });
  // await autoScroll(page);
  // await page.waitForTimeout(3000);

  // const nftData = await page.evaluate(() => {
  //   const list = [];
  //   const nftRows = document.querySelectorAll(".db-table-row");
  //   nftRows.forEach(row => {
  //     const cells = Array.from(row.querySelectorAll(".db-table-cell"));
  //     if (cells.length >= 3) {
  //       let collection = cells[0]?.innerText.trim() || "";
  //       // Clean up collection name (remove counts or numbers if they are prefixed)
  //       collection = collection.split('\n').pop().trim();

  //       list.push({
  //         collection,
  //         amount: cells[1]?.innerText.trim(),
  //         avg_price: cells[2]?.innerText.trim()
  //       });
  //     }
  //   });
  //   return list;
  // });
  // mergedData.nfts = nftData;

  await fs.writeFile(OUTPUT_PATH, JSON.stringify(mergedData, null, 2));
  console.log(`Data saved to ${OUTPUT_PATH}`);

  await browser.close();
})();
