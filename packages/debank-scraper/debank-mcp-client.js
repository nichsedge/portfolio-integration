const { Client } = require("@modelcontextprotocol/sdk/client/index.js");
const {
  StdioClientTransport,
} = require("@modelcontextprotocol/sdk/client/stdio.js");
const { spawn } = require("child_process");

async function useDebankMCP() {
  // Start the MCP server process
  const serverProcess = spawn("node", ["debank-mcp-server.js"], {
    stdio: ["pipe", "pipe", "inherit"],
  });

  // Create client and connect to server
  const transport = new StdioClientTransport({
    command: "node",
    args: ["debank-mcp-server.js"],
  });

  const client = new Client(
    {
      name: "debank-client",
      version: "1.0.0",
    },
    {
      capabilities: {},
    }
  );

  try {
    await client.connect(transport);

    // List available tools
    const tools = await client.listTools();
    console.log(
      "Available tools:",
      tools.tools.map((t) => t.name)
    );

    // Scrape a Debank profile
    const result = await client.callTool({
      name: "scrape_debank_profile",
      arguments: {
        address: "1d014371800dd8c97c1fe682ca7b30dafb16ea9a", // Your address
        headless: true,
      },
    });

    console.log("Profile data:", JSON.parse(result.content[0].text));
  } catch (error) {
    console.error("Error:", error);
  } finally {
    await client.close();
    serverProcess.kill();
  }
}

// Alternative: Direct CLI usage
// Just pipe JSON to the server:
const directUsage = `
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scrape_debank_profile","arguments":{"address":"1d014371800dd8c97c1fe682ca7b30dafb16ea9a"}}}' | node debank-mcp-server.js
`;

useDebankMCP();
