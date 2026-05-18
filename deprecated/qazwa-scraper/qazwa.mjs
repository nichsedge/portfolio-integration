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

const QAZWA_EMAIL = process.env.QAZWA_EMAIL;
const QAZWA_PASSWORD = process.env.QAZWA_PASSWORD;

if (!QAZWA_EMAIL || !QAZWA_PASSWORD) {
  console.error('Error: QAZWA_EMAIL and QAZWA_PASSWORD must be set in .env file');
  process.exit(1);
}

const LOGIN_URL = 'https://app.qazwa.id/login';
const PORTFOLIO_URL = 'https://app.qazwa.id/portfolio';

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
const OUTPUT_PATH = path.join(dataDir, `${currentDate}_raw_qazwa.json`);
const dirname = path.dirname(OUTPUT_PATH);

async function ensureDirectoryExists() {
  try {
    await fs.mkdir(dirname, { recursive: true });
    console.log(`Directory '${dirname}' exists or was created.`);
  } catch (err) {
    console.error(`Failed to create directory:`, err);
  }
}

async function login(page) {
  console.log('Navigating to login page...');
  
  // Wait for page to fully load with more耐心
  await page.goto(LOGIN_URL, { waitUntil: 'networkidle' });
  
  // Wait longer for JavaScript frameworks to render
  console.log('Waiting for page to fully render...');
  await page.waitForTimeout(5000);

  // Debug: Take a screenshot and log page content
  console.log('Current URL:', page.url());
  console.log('Page title:', await page.title());
  
  // Try to find all input elements for debugging
  const allInputs = await page.$$('input');
  console.log(`Found ${allInputs.length} input elements on page`);
  
  for (let i = 0; i < allInputs.length; i++) {
    const input = allInputs[i];
    const type = await input.getAttribute('type');
    const name = await input.getAttribute('name');
    const placeholder = await input.getAttribute('placeholder');
    const id = await input.getAttribute('id');
    console.log(`Input ${i}: type=${type}, name=${name}, placeholder=${placeholder}, id=${id}`);
  }

  // If still no inputs, try waiting for specific elements that might indicate the page is ready
  if (allInputs.length === 0) {
    console.log('No inputs found, waiting for page to be fully interactive...');
    await page.waitForTimeout(3000);
    
    // Try to wait for any element that might indicate the page is loaded
    try {
      await page.waitForSelector('body > *', { timeout: 10000 });
      console.log('Page content loaded');
    } catch (e) {
      console.warn('Could not wait for page content');
    }
    
    // Check again for inputs
    const inputsAfterWait = await page.$$('input');
    console.log(`Found ${inputsAfterWait.length} input elements after waiting`);
  }

  // Wait for login form with longer timeout
  try {
    await page.waitForSelector('input, form, button', { timeout: 20000 });
    console.log('Login form elements found');
  } catch (e) {
    console.warn('Could not find login form elements, trying to proceed...');
  }

  // Try multiple selectors for email input
  const emailSelectors = [
    'input[name="email"]',
    'input[type="email"]',
    '#email',
    '.email',
    'input[placeholder*="email" i]',
    'input[placeholder*="Email" i]',
    'input[placeholder*="e-mail" i]',
    'input[placeholder*="E-mail" i]',
    'input:not([type="password"]):not([type="submit"])'
  ];

  let emailInput = null;
  for (const selector of emailSelectors) {
    emailInput = await page.$(selector);
    if (emailInput) {
      console.log(`Found email input using selector: ${selector}`);
      break;
    }
  }

  if (!emailInput) {
    console.error('Email input not found with any selector');
    // Take screenshot for debugging
    await page.screenshot({ path: path.join(dataDir, 'screenshots', currentDate, 'login_page.png') });
    return false;
  }

  // Fill in email
  await emailInput.fill(QAZWA_EMAIL);
  console.log('Email filled');

  // Try multiple selectors for password input
  const passwordSelectors = [
    'input[name="password"]',
    'input[type="password"]',
    '#password',
    '.password',
    'input[placeholder*="password" i]',
    'input[placeholder*="Password" i]',
    'input[placeholder*="kata sandi" i]',
    'input[placeholder*="Kata Sandi" i]'
  ];

  let passwordInput = null;
  for (const selector of passwordSelectors) {
    passwordInput = await page.$(selector);
    if (passwordInput) {
      console.log(`Found password input using selector: ${selector}`);
      break;
    }
  }

  if (!passwordInput) {
    console.error('Password input not found with any selector');
    return false;
  }

  // Fill in password
  await passwordInput.fill(QAZWA_PASSWORD);
  console.log('Password filled');

  // Try multiple selectors for login button
  const loginButtonSelectors = [
    'button[type="submit"]',
    'button:has-text("Login")',
    'button:has-text("Sign In")',
    'button:has-text("Sign in")',
    'button:has-text("Masuk")',
    'button:has-text("LOGIN")',
    '.login-button',
    '.btn-login',
    'button:has-text("Submit")',
    'button:has-text("Kirim")'
  ];

  let loginButton = null;
  for (const selector of loginButtonSelectors) {
    loginButton = await page.$(selector);
    if (loginButton) {
      console.log(`Found login button using selector: ${selector}`);
      break;
    }
  }

  if (!loginButton) {
    console.error('Login button not found with any selector');
    return false;
  }

  // Click login button
  await loginButton.click();
  console.log('Login button clicked');

  // Wait for navigation or dashboard
  try {
    await page.waitForURL(PORTFOLIO_URL, { timeout: 20000 });
    console.log('Successfully logged in and redirected to portfolio');
    return true;
  } catch (e) {
    console.warn('Did not redirect to portfolio URL, checking for dashboard...');
    // Try alternative selectors for dashboard
    try {
      await page.waitForSelector('div[class*="portfolio"], .portfolio, #portfolio, [data-testid*="portfolio"]', { timeout: 15000 });
      console.log('Dashboard/portfolio page loaded');
      return true;
    } catch (e2) {
      console.error('Could not confirm successful login');
      // Take screenshot for debugging
      await page.screenshot({ path: path.join(dataDir, 'screenshots', currentDate, 'after_login.png') });
      return false;
    }
  }
}

async function extractPortfolioData(page) {
  console.log('Extracting portfolio data...');
  
  // Try to get portfolio data from the page
  const portfolioData = await page.evaluate(() => {
    const data = {
      summary: {},
      holdings: [],
      transactions: [],
      rawHtml: null
    };

    // Try to extract summary information
    const summaryElements = document.querySelectorAll('[class*="summary"], [class*="total"], [class*="balance"], [class*="asset"]');
    summaryElements.forEach(el => {
      const text = el.innerText?.trim();
      if (text && text.length > 0 && text.length < 100) {
        const key = el.className?.split(' ').find(c => c.includes('total') || c.includes('balance') || c.includes('asset')) || 'value';
        data.summary[key] = text;
      }
    });

    // Try to find portfolio table or list
    const tables = document.querySelectorAll('table, div[class*="table"], div[class*="list"]');
    tables.forEach((table, index) => {
      const rows = table.querySelectorAll('tr, div[class*="row"], div[class*="item"]');
      if (rows.length > 0) {
        const tableData = [];
        rows.forEach(row => {
          const cells = row.querySelectorAll('td, div[class*="cell"], div[class*="col"]');
          if (cells.length > 0) {
            const rowData = {};
            cells.forEach((cell, cellIndex) => {
              const text = cell.innerText?.trim();
              if (text) {
                rowData[`col${cellIndex}`] = text;
              }
            });
            if (Object.keys(rowData).length > 0) {
              tableData.push(rowData);
            }
          }
        });
        if (tableData.length > 0) {
          data.holdings.push({ tableIndex: index, data: tableData });
        }
      }
    });

    // Try to extract cards or tiles
    const cards = document.querySelectorAll('[class*="card"], [class*="tile"], [class*="widget"]');
    cards.forEach((card, index) => {
      const title = card.querySelector('[class*="title"], [class*="header"], h1, h2, h3, h4');
      const value = card.querySelector('[class*="value"], [class*="amount"], [class*="balance"]');
      if (title && value) {
        data.summary[title.innerText.trim()] = value.innerText.trim();
      }
    });

    // Get all text content for debugging
    const bodyText = document.body?.innerText || '';
    data.rawHtml = bodyText.substring(0, 5000); // First 5000 chars

    return data;
  });

  return portfolioData;
}

async function extractDetailedPortfolio(page) {
  console.log('Extracting detailed portfolio information...');
  
  const detailedData = await page.evaluate(() => {
    const data = {
      accounts: [],
      assets: [],
      summary: {},
      metadata: {}
    };

    // Try to find account information
    const accountSelectors = [
      '[class*="account"]',
      '[class*="wallet"]',
      '[class*="portfolio"]',
      '[data-testid*="account"]',
      '[data-testid*="wallet"]'
    ];

    accountSelectors.forEach(selector => {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        const text = el.innerText?.trim();
        if (text && text.length > 0 && text.length < 200) {
          data.accounts.push({
            selector: selector,
            text: text,
            class: el.className
          });
        }
      });
    });

    // Try to find asset information
    const assetSelectors = [
      '[class*="asset"]',
      '[class*="holding"]',
      '[class*="position"]',
      '[class*="token"]',
      '[class*="coin"]',
      '[data-testid*="asset"]',
      '[data-testid*="holding"]'
    ];

    assetSelectors.forEach(selector => {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        const text = el.innerText?.trim();
        if (text && text.length > 0 && text.length < 100) {
          data.assets.push({
            selector: selector,
            text: text,
            class: el.className
          });
        }
      });
    });

    // Try to find summary information
    const summarySelectors = [
      '[class*="summary"]',
      '[class*="total"]',
      '[class*="balance"]',
      '[class*="value"]',
      '[data-testid*="summary"]',
      '[data-testid*="total"]'
    ];

    summarySelectors.forEach(selector => {
      const elements = document.querySelectorAll(selector);
      elements.forEach(el => {
        const text = el.innerText?.trim();
        if (text && text.length > 0 && text.length < 100) {
          const key = el.className?.split(' ').find(c => 
            c.includes('total') || c.includes('balance') || c.includes('value')
          ) || 'value';
          data.summary[key] = text;
        }
      });
    });

    // Get all links for navigation
    const links = document.querySelectorAll('a[href]');
    data.metadata.links = Array.from(links).map(link => ({
      href: link.getAttribute('href'),
      text: link.innerText?.trim()
    })).filter(l => l.href && l.href.length > 0);

    // Get all buttons
    const buttons = document.querySelectorAll('button');
    data.metadata.buttons = Array.from(buttons).map(btn => ({
      text: btn.innerText?.trim(),
      class: btn.className,
      type: btn.type
    })).filter(b => b.text && b.text.length > 0);

    return data;
  });

  return detailedData;
}

async function captureScreenshots(page) {
  console.log('Capturing screenshots...');
  const screenshotsDir = path.join(dataDir, 'screenshots', currentDate);
  await fs.mkdir(screenshotsDir, { recursive: true });

  try {
    await page.screenshot({ path: path.join(screenshotsDir, 'full.png'), fullPage: true });
    console.log('Full page screenshot saved');
  } catch (e) {
    console.warn('Could not capture full page screenshot:', e.message);
  }

  try {
    await page.screenshot({ path: path.join(screenshotsDir, 'viewport.png') });
    console.log('Viewport screenshot saved');
  } catch (e) {
    console.warn('Could not capture viewport screenshot:', e.message);
  }
}

(async () => {
  await ensureDirectoryExists();

  const browser = await chromium.launch({ 
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  });
  
  const page = await context.newPage();

  try {
    // Login
    const loginSuccess = await login(page);
    if (!loginSuccess) {
      console.error('Login failed. Please check credentials and try again.');
      await browser.close();
      process.exit(1);
    }

    // Wait a bit for page to load
    await page.waitForTimeout(3000);

    // Navigate to portfolio page if not already there
    try {
      await page.goto(PORTFOLIO_URL, { waitUntil: 'domcontentloaded', timeout: 10000 });
      console.log('Navigated to portfolio page');
    } catch (e) {
      console.warn('Could not navigate to portfolio URL, continuing with current page');
    }

    // Capture screenshots
    await captureScreenshots(page);

    // Extract data
    const basicData = await extractPortfolioData(page);
    const detailedData = await extractDetailedPortfolio(page);

    // Combine all data
    const mergedData = {
      timestamp: new Date().toISOString(),
      loginEmail: QAZWA_EMAIL,
      portfolioUrl: PORTFOLIO_URL,
      basicData,
      detailedData,
      pageUrl: page.url(),
      pageTitle: await page.title()
    };

    // Save to file
    await fs.writeFile(OUTPUT_PATH, JSON.stringify(mergedData, null, 2));
    console.log(`Data saved to ${OUTPUT_PATH}`);

    // Also log to console
    console.log('\n=== QAZWA PORTFOLIO DATA ===');
    console.log(JSON.stringify(mergedData, null, 2));

  } catch (error) {
    console.error('Error during scraping:', error);
    
    // Try to capture error screenshot
    try {
      const errorDir = path.join(dataDir, 'screenshots', currentDate);
      await fs.mkdir(errorDir, { recursive: true });
      await page.screenshot({ path: path.join(errorDir, 'error.png') });
    } catch (e) {
      console.warn('Could not capture error screenshot');
    }
  } finally {
    await browser.close();
  }
})();