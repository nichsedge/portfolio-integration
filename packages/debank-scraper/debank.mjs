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
    // This will create the directory if it doesn't exist.
    // It will do nothing if it already exists.
    // It will create parent directories if needed due to { recursive: true }.
    await fs.mkdir(dirname, { recursive: true });
    console.log(`Directory '${dirname}' exists or was created.`);
  } catch (err) {
    // This catch block will only execute for actual errors
    // (e.g., lack of permissions), not if the directory exists.
    console.error(`Failed to create directory:`, err);
  }
}
ensureDirectoryExists();

async function autoScroll(page) {
  await page.evaluate(async () => {
    await new Promise((resolve) => {
      let totalHeight = 0;
      const distance = 500;
      const timer = setInterval(() => {
        const scrollHeight = document.body.scrollHeight;
        window.scrollBy(0, distance);
        totalHeight += distance;

        if (totalHeight >= scrollHeight) {
          clearInterval(timer);
          resolve();
        }
      }, 300);
    });
  });
}

async function extractAssetData(page) {
  return await page.evaluate(() => {
    const allElements = document.querySelectorAll("*");
    for (let element of allElements) {
      const text = element.textContent || "";
      const match = text.match(/\$[\d,]+.*?[+\-]\d+\.\d+%/);
      if (match) {
        const dollarMatch = text.match(/\$[\d,]+/);
        const percentMatch = text.match(/[+\-]\d+\.\d+%/);
        return {
          found: true,
          amount: dollarMatch ? dollarMatch[0] : "",
          change: percentMatch ? percentMatch[0] : "",
        };
      }
    }
    return { found: false, message: "No asset data found" };
  });
}

async function extractProfileData(page) {
  return await page.evaluate(() => {
    const data = {};
    const items = document.querySelectorAll("div[class*='HeaderInfo_infoItem']");
    items.forEach((item) => {
      if (item.closest("a")) return;
      const title = item.querySelector("div[class*='HeaderInfo_title'], div[class*='infoItemTitle']")?.innerText.trim();
      const value = item.querySelector("div[class*='HeaderInfo_value'], div[class*='infoItemValue']")?.innerText.trim();
      if (title && value) data[title] = value;
    });

    // Also try to get the total net worth specifically
    const totalAsset = document.querySelector("div[class*='HeaderInfo_totalAssetInner'], div[class*='totalAsset']");
    if (totalAsset) {
      data['Total Assets'] = totalAsset.innerText.trim();
    }

    return data;
  });
}

async function extractWallets(page) {
  return await page.evaluate(() => {
    const table = document.querySelector("div[class*='TokenWallet_table']");
    if (!table) return [];

    const headerEls = table.querySelectorAll("div[class*='db-table-headerItem']");
    const headers = Array.from(headerEls).map((el) => el.innerText.trim());

    const rowEls = table.querySelectorAll("div[class*='db-table-row']");
    return Array.from(rowEls).map((row) => {
      const cells = row.querySelectorAll("div[class*='db-table-cell']");

      // Extract the href and chain
      const tokenLink = cells[0]?.querySelector("a");
      let chain = "";
      if (tokenLink?.getAttribute("href")) {
        const hrefParts = tokenLink.getAttribute("href").split("/");
        if (hrefParts.length >= 3) {
          chain = hrefParts[2]; // /token/{chain}/{token} -> get {chain}
        }
      }

      // Fallback for chain: check for icon alt
      if (!chain) {
        const chainIcon = cells[0]?.querySelector('img[class*="ChainIcon"]');
        if (chainIcon) {
          const alt = chainIcon.alt || "";
          if (alt) chain = alt.toLowerCase();
        }
      }

      const values = Array.from(cells).map((cell, i) => {
        return cell.innerText.trim();
      });

      const rowObj = {};
      headers.forEach((key, i) => {
        rowObj[key] = values[i] || "";
      });
      rowObj.chain = chain;

      // Ensure 'name' is available for the integrator
      if (rowObj.Token) {
        rowObj.name = rowObj.Token;
      }

      return rowObj;
    });
  });
}


async function extractProtocols(page) {
  return await page.$$eval('div[class*="Project_project__"]', (projects) => {
    return projects.map((project) => {
      // Try multiple selectors for protocol name
      const nameSelectors = [
        'span[class*="ProjectTitle_protocolLink"]',
        'a[class*="protocolLink"]',
        'div[class*="ProjectTitle_name"]',
        'div[class*="projectTitle-name"]',
        '[class*="protocolName"]'
      ];

      let protocolName = null;
      for (const selector of nameSelectors) {
        const el = project.querySelector(selector);
        if (el && el.innerText.trim()) {
          protocolName = el.innerText.trim();
          break;
        }
      }

      // Fallback if still null
      if (!protocolName) {
        const firstLink = project.querySelector('a');
        if (firstLink) protocolName = firstLink.innerText.trim();
      }

      const usdValueElem = project.querySelector('div[class*="projectTitle-number"], [class*="usdValue"]');
      const usdValue = usdValueElem?.innerText.trim() || null;

      // Extract protocol ID from any link containing protocol
      let protocolId = null;
      const allLinks = Array.from(project.querySelectorAll('a'));
      const protocolLink = allLinks.find(a => a.getAttribute('href')?.includes('/protocol/'));
      if (protocolLink) {
        const href = protocolLink.getAttribute('href');
        const match = href.match(/\/protocol\/([^/]+)/);
        if (match) protocolId = match[1];
      }

      // Extract chain icon
      const chainIcon = project.querySelector('img[class*="ProjectTitle_chainIcon"], img[class*="ChainIcon"], img[class*="ProjectTitle_chain_"]');
      let chain = null;
      if (chainIcon) {
        chain = chainIcon.alt || chainIcon.getAttribute('data-name') || chainIcon.getAttribute('title');
      }

      // If still no chain, look for it in the protocol card area
      if (!chain) {
        const potentialChainIcon = project.querySelector('div[class*="ProjectTitle_chainIcon"] img, .ChainIcon img');
        if (potentialChainIcon) {
          chain = potentialChainIcon.alt || potentialChainIcon.getAttribute('data-name');
        }
      }

      // Extract headers
      const headerElems = project.querySelectorAll('div[class*="table_header__"] > div > span, div[class*="db-table-headerItem"], div[class*="Project_project__"] div.db-table-headerItem');
      const headers = Array.from(headerElems)
        .map((el) => el.innerText.trim())
        .filter((txt) => txt !== "");

      // Extract rows
      const rowElems = project.querySelectorAll('div[class*="table_contentRow__"], div[class*="db-table-row"]');
      const dataRows = Array.from(rowElems).map((row) => {
        const cells = row.querySelectorAll(':scope > div, div[class*="db-table-cell"]');
        const values = Array.from(cells).map((cell) => cell.innerText.trim());

        const obj = {};
        headers.forEach((key, i) => {
          const val = values[i] || null;
          obj[key] = val;

          // Integrator compatibility: extract token symbol if possible
          const lowerKey = key.toLowerCase();
          if (['balance', 'supplied', 'borrowed', 'token', 'asset', 'pool', 'staked', 'collateral'].some(k => lowerKey.includes(k))) {
            if (val && !obj.token) {
              const match = val.match(/^([\d,.]+)\s+([A-Z0-9a-z./]+)/);
              if (match) {
                obj.amount = match[1].replace(/,/g, '');
                obj.token = { symbol: match[2] };
              } else {
                const parts = val.split('\n')[0].trim().split(/\s+/);
                if (parts.length === 2 && parts[0] && !isNaN(parts[0].replace(/,/g, ''))) {
                  obj.amount = parts[0].replace(/,/g, '');
                  obj.token = { symbol: parts[1] };
                } else if (parts.length === 1 && parts[0] && parts[0].length < 15) {
                  // Only set as token if it looks like a symbol (doesn't start with $)
                  if (!parts[0].startsWith('$')) {
                    obj.token = { symbol: parts[0] };
                  }
                }
              }
            }
          }
        });

        // Final fallback for amount
        if (!obj.amount && obj['Amount']) obj.amount = obj['Amount'].replace(/,/g, '');

        return obj;
      });

      return {
        id: protocolId,
        name: protocolName,
        usdValue,
        chain,
        data: dataRows,
      };
    });
  });
}


(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  await page.goto(PROFILE_URL, { waitUntil: "domcontentloaded" });

  // Wait for any stable element that signals page structure is ready
  // Using a more generic selector for the header area
  try {
    await page.waitForSelector("div[class*='HeaderInfo_headerInfoWrap'], div[class*='HeaderInfo_totalAsset'], div[class*='HeaderInfo']", { timeout: 20000 });
  } catch (e) {
    console.warn("Header selector timeout, trying to proceed anyway...");
  }

  // Scroll to load lazy content
  await autoScroll(page);

  // Give it a short pause for final requests to complete
  await page.waitForTimeout(3000);

  const assetData = await extractAssetData(page);
  const profileData = await extractProfileData(page);
  const wallets = await extractWallets(page);
  const protocols = await extractProtocols(page);

  const mergedData = {
    assetData,
    profileData,
    wallets,
    protocols,
    timestamp: new Date().toISOString(),
    profileUrl: PROFILE_URL,
  };

  await fs.writeFile(OUTPUT_PATH, JSON.stringify(mergedData, null, 2));
  console.log(`Data saved to ${OUTPUT_PATH}`);

  await browser.close();
})();
