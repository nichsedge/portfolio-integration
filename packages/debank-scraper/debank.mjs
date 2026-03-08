import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';

import 'dotenv/config';
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
  await page.goto(PROFILE_URL, { waitUntil: "domcontentloaded" });

  try {
    // Wait for the main asset value to appear (using more robust selectors)
    await page.waitForSelector("div[class*='HeaderInfo_totalAssetInner'], div[class*='HeaderInfo_totalAsset'], div[class*='HeaderInfo_totalAssetValue']", { timeout: 10000 });
  } catch (e) {
    console.warn("Timed out waiting for total assets selector after 10s. Continuing...");
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
    // Target both the summary grid cards and the detailed project sections
    const protocolItems = document.querySelectorAll("[class*='ProjectCell_assetsItem'], [class*='Project_project'], [class*='ProjectCell_projectCell'], [class*='ProjectCell_assetsItemWrap']");
    protocolItems.forEach(item => {
      const nameEl = item.querySelector("[class*='ProjectCell_assetsItemNameText'], [class*='Project_projectName'], [class*='ProjectTitle_name'], [class*='ProjectCell_name']");
      const valueEl = item.querySelector("[class*='ProjectCell_assetsItemWorth'], [class*='Project_projectValue'], [class*='projectTitle-number'], [class*='ProjectCell_value']");

      if (nameEl) {
        const name = nameEl.innerText.trim();
        const value = valueEl ? valueEl.innerText.trim() : null;

        // Filter out 'Wallet' as it's already handled, and avoid duplicates
        if (name && name !== 'Wallet' && !data.protocols.find(p => p.name === name)) {
          data.protocols.push({ name, value });
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
