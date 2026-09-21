/**
 * streamforge connect <api-url>
 *
 * Sets the API URL for an existing (or new) StreamForge config, tests the
 * connection by hitting the /health endpoint, and saves the result.
 */

'use strict';

const http  = require('http');
const https = require('https');
const { loadConfig, saveConfig, CONFIG_FILE, c } = require('../config');

// ── health check ────────────────────────────────────────────────────────────
function checkHealth(apiUrl) {
  return new Promise((resolve) => {
    const url = new URL(apiUrl.replace(/\/+$/, '') + '/health');
    const client = url.protocol === 'https:' ? https : http;

    const req = client.get(url, { timeout: 10000 }, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => {
        resolve({ ok: res.statusCode >= 200 && res.statusCode < 400, status: res.statusCode, body });
      });
    });

    req.on('timeout', () => { req.destroy(); resolve({ ok: false, status: 0, body: 'Request timed out' }); });
    req.on('error', (err) => resolve({ ok: false, status: 0, body: err.message }));
  });
}

// ── main ────────────────────────────────────────────────────────────────────
module.exports = async function connect(argv) {
  // --help
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(`\n${c.bold}streamforge connect <api-url>${c.reset}`);
    console.log(`\nConnect to a StreamForge deployment and save the config.\n`);
    console.log(`${c.bold}ARGUMENTS${c.reset}`);
    console.log(`  api-url    Base URL of the StreamForge API\n`);
    console.log(`${c.bold}EXAMPLES${c.reset}`);
    console.log(`  streamforge connect https://abc.execute-api.us-west-2.amazonaws.com/v1\n`);
    return;
  }

  // Positional: first non-flag argument is the api-url
  const apiUrl = argv.find((a) => !a.startsWith('-'));

  if (!apiUrl) {
    console.error(`${c.red}Error: API URL is required.${c.reset}`);
    console.error(`Usage: streamforge connect <api-url>\n`);
    process.exit(1);
  }

  // Validate URL format
  try {
    new URL(apiUrl);
  } catch {
    console.error(`${c.red}Error: Invalid URL — ${apiUrl}${c.reset}`);
    process.exit(1);
  }

  console.log(`\n${c.cyan}${c.bold}StreamForge Connect${c.reset}\n`);
  console.log(`  API URL: ${c.bold}${apiUrl}${c.reset}\n`);

  // Test health
  process.stdout.write(`${c.dim}Testing connection...${c.reset} `);
  const health = await checkHealth(apiUrl);

  if (health.ok) {
    console.log(`${c.green}OK${c.reset} (HTTP ${health.status})`);
  } else {
    console.log(`${c.yellow}Unreachable${c.reset}`);
    console.log(`  ${c.dim}Status: ${health.status || 'N/A'} — ${health.body}${c.reset}`);
    console.log(`\n${c.yellow}Warning:${c.reset} Could not reach /health. Config will be saved anyway.`);
  }

  // Merge with existing config
  const existing = loadConfig();
  const config = {
    ...existing,
    api_url: apiUrl,
  };

  const savedPath = saveConfig(config);
  console.log(`\n${c.green}Config saved${c.reset} to ${savedPath}`);
  console.log(`Run ${c.cyan}streamforge status${c.reset} to see deployment details.\n`);
};
