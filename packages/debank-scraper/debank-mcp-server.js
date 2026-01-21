const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const {
  StdioServerTransport,
} = require("@modelcontextprotocol/sdk/server/stdio.js");
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require("@modelcontextprotocol/sdk/types.js");
const { chromium } = require("playwright");

class DebankServer {
  constructor() {
    this.server = new Server(
      {
        name: "debank-server",
        version: "0.1.0",
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();

    this.server.onerror = (error) => console.error("[MCP Error]", error);
    process.on("SIGINT", async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: "scrape_debank_profile",
          description:
            "Scrape Debank profile data including assets, wallets, and protocols",
          inputSchema: {
            type: "object",
            properties: {
              address: {
                type: "string",
                description:
                  "Ethereum wallet address (without 0x prefix or with)",
              },
              headless: {
                type: "boolean",
                description: "Run browser in headless mode",
                default: true,
              },
            },
            required: ["address"],
          },
        },
      ],
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      if (request.params.name === "scrape_debank_profile") {
        return await this.scrapeDebankProfile(request.params.arguments);
      }
      throw new Error(`Unknown tool: ${request.params.name}`);
    });
  }

  async scrapeDebankProfile({ address, headless = true }) {
    const cleanAddress = address.startsWith("0x") ? address : `0x${address}`;
    const profileUrl = `https://debank.com/profile/${cleanAddress}`;

    const browser = await chromium.launch({ headless });
    const page = await browser.newPage();

    try {
      await page.goto(profileUrl, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(5000);

      const assetData = await this.extractAssetData(page);
      const profileData = await this.extractProfileData(page);
      const wallets = await this.extractWallets(page);
      const protocols = await this.extractProtocols(page);

      const result = {
        address: cleanAddress,
        assetData,
        profileData,
        wallets,
        protocols,
        timestamp: new Date().toISOString(),
        profileUrl,
      };

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result, null, 2),
          },
        ],
      };
    } finally {
      await browser.close();
    }
  }

  async extractAssetData(page) {
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

  async extractProfileData(page) {
    try {
      await page.waitForSelector("div[class*='HeaderInfo_totalAssetInner']", {
        timeout: 10000,
      });
      return await page.evaluate(() => {
        const data = {};
        const items = document.querySelectorAll(
          "div[class*='HeaderInfo_infoItem']"
        );
        items.forEach((item) => {
          if (item.closest("a")) return;
          const title = item
            .querySelector("div[class*='HeaderInfo_title']")
            ?.innerText.trim();
          const value = item
            .querySelector("div[class*='HeaderInfo_value']")
            ?.innerText.trim();
          if (title && value) data[title] = value;
        });
        return data;
      });
    } catch (error) {
      return { error: "Failed to extract profile data" };
    }
  }

  async extractWallets(page) {
    try {
      await page.waitForSelector("div[class*='TokenWallet_table']", {
        timeout: 10000,
      });
      return await page.evaluate(() => {
        const table = document.querySelector("div[class*='TokenWallet_table']");
        if (!table) return [];
        const headerEls = table.querySelectorAll(
          "div[class*='db-table-headerItem']"
        );
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
          const rowObj = {};
          headers.forEach((key, i) => {
            rowObj[key] = values[i] || "";
          });
          return rowObj;
        });
      });
    } catch (error) {
      return [];
    }
  }

  async extractProtocols(page) {
    try {
      await page.waitForSelector("div[class^='table_contentRow__']", {
        timeout: 10000,
      });
      const headerGroups = await page.$$eval(
        "div[class^='table_header__']",
        (headers) =>
          headers.map((header) => {
            const spans = Array.from(header.querySelectorAll("div > span"));
            return spans.map((span) => span.innerText.trim());
          })
      );
      const valueGroups = await page.$$eval(
        "div[class^='table_contentRow__']",
        (rows) =>
          rows.map((row) => {
            const spans = Array.from(row.querySelectorAll("div > span"));
            return spans.map((span) => span.innerText.trim());
          })
      );
      return valueGroups.map((values, index) => {
        const headers = headerGroups[index] || [];
        const obj = {};
        headers.forEach((key, i) => {
          obj[key] = values[i] || null;
        });
        return obj;
      });
    } catch (error) {
      return [];
    }
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("Debank MCP server running on stdio");
  }
}

const server = new DebankServer();
server.run().catch(console.error);
