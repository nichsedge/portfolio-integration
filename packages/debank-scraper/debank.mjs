import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';

import 'dotenv/config';
const EVM_ADDRESS = process.env.EVM_ADDRESS || "your_default_address_here";

const PROFILE_URL = `https://debank.com/profile/${EVM_ADDRESS}`;

const getDataDir = () => {
  return process.env.PORTFOLIO_DATA_DIR || process.env.DATA_DIR || '/home/al/Projects/.data/portfolio';
};

const getCurrentDate = () => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};

const currentDate = getCurrentDate();
const dataDir = getDataDir();
const OUTPUT_PATH = `${dataDir}/${currentDate}_raw_debank.json`;
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
  // await page.waitForSelector("div[class*='HeaderInfo_totalAssetInner']", { timeout: 10000 });
  return await page.evaluate(() => {
    const data = {};
    const items = document.querySelectorAll("div[class*='HeaderInfo_infoItem']");
    items.forEach((item) => {
      if (item.closest("a")) return;
      const title = item.querySelector("div[class*='HeaderInfo_title']")?.innerText.trim();
      const value = item.querySelector("div[class*='HeaderInfo_value']")?.innerText.trim();
      if (title && value) data[title] = value;
    });
    return data;
  });
}

async function extractWallets(page) {
  // await page.waitForSelector("div[class*='TokenWallet_table']", { timeout: 10000 });

  return await page.evaluate(() => {
    const table = document.querySelector("div[class*='TokenWallet_table']");
    if (!table) return [];

    const headerEls = table.querySelectorAll("div[class*='db-table-headerItem']");
    const headers = Array.from(headerEls).map((el) => el.innerText.trim());

    const rowEls = table.querySelectorAll("div[class*='db-table-row']");
    return Array.from(rowEls).map((row) => {
      const cells = row.querySelectorAll("div[class*='db-table-cell']");
      const values = Array.from(cells).map((cell, i) => {
        if (i === 0) {
          const tokenLink = cell.querySelector("a");
          return tokenLink?.innerText.trim() || "";
        }
        return cell.innerText.trim();
      });

      // Extract the href and chain
      const tokenLink = cells[0]?.querySelector("a");
      let chain = "";
      if (tokenLink?.getAttribute("href")) {
        const hrefParts = tokenLink.getAttribute("href").split("/");
        if (hrefParts.length >= 3) {
          chain = hrefParts[2]; // /token/{chain}/{token} -> get {chain}
        }
      }

      const rowObj = {};
      headers.forEach((key, i) => {
        rowObj[key] = values[i] || "";
      });
      rowObj.chain = chain;

      return rowObj;
    });
  });
}


async function extractProtocols(page) {
  return await page.$$eval('div[class^="Project_project__"]', (projects) => {
    return projects.map((project) => {
      const nameElem = project.querySelector('span[class^="ProjectTitle_protocolLink"]');
      const usdValueElem = project.querySelector('div[class^="projectTitle-number"]');

      const protocolName = nameElem?.innerText.trim() || null;
      const usdValue = usdValueElem?.innerText.trim() || null;

      // Extract headers (skip empty placeholder)
      const headerElems = project.querySelectorAll('div[class^="table_header__"] > div > span');
      const headers = Array.from(headerElems)
        .map((el) => el.innerText.trim())
        .filter((txt) => txt !== "");

      // Extract rows
      const rowElems = project.querySelectorAll('div[class^="table_contentRow__"]');
      const rows = Array.from(rowElems).map((row) => {
        // take direct child divs = each cell
        const cells = row.querySelectorAll(':scope > div');
        return Array.from(cells).map((cell) => cell.innerText.trim());
      });

      // Merge headers with values
      const data = rows.map((values) => {
        const obj = {};
        headers.forEach((key, i) => {
          obj[key] = values[i] || null;
        });
        return obj;
      });

      return {
        name: protocolName,
        usdValue,
        data,
      };
    });
  });
}


(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  await page.goto(PROFILE_URL, { waitUntil: "domcontentloaded" });
  // Wait for any stable element that signals page structure is ready
  await page.waitForSelector("div[class*='HeaderInfo']", { timeout: 20000 });

  // Scroll to load lazy content
  await autoScroll(page);

  // Give it a short pause for final requests to complete
  await page.waitForTimeout(2000);

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
