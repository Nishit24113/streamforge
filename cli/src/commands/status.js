/**
 * streamforge status
 *
 * Shows deployment health, pipeline count, event stats, and anomaly count
 * by querying the API and analytics endpoints.
 */

'use strict';

const http  = require('http');
const https = require('https');
const { loadConfig, c } = require('../config');

// ── HTTP GET helper ─────────────────────────────────────────────────────────
function httpGet(baseUrl, path) {
  return new Promise((resolve) => {
    if (!baseUrl) return resolve({ ok: false, status: 0, body: 'URL not configured' });

    const endpoint = baseUrl.replace(/\/+$/, '') + path;
    let url;
    try { url = new URL(endpoint); } catch { return resolve({ ok: false, status: 0, body: 'Invalid URL' }); }

    const client = url.protocol === 'https:' ? https : http;

    const req = client.get(url, { timeout: 10000 }, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => {
        let parsed;
        try { parsed = JSON.parse(body); } catch { parsed = body; }
        resolve({ ok: res.statusCode >= 200 && res.statusCode < 400, status: res.statusCode, body: parsed });
      });
    });

    req.on('timeout', () => { req.destroy(); resolve({ ok: false, status: 0, body: 'Request timed out' }); });
    req.on('error', (err) => resolve({ ok: false, status: 0, body: err.message }));
  });
}

// ── formatting helpers ──────────────────────────────────────────────────────
function statusIcon(ok) {
  return ok ? `${c.green}●${c.reset}` : `${c.red}●${c.reset}`;
}

function formatNumber(n) {
  if (typeof n !== 'number') return 'N/A';
  return n.toLocaleString();
}

// ── main ────────────────────────────────────────────────────────────────────
module.exports = async function status(argv) {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(`\n${c.bold}streamforge status${c.reset}`);
    console.log(`\nShow deployment health, pipeline count, event stats, and anomalies.\n`);
    console.log(`Reads config from ${c.cyan}${'.streamforge.json'}${c.reset} or environment variables.\n`);
    return;
  }

  const config = loadConfig({ required: true });

  console.log(`\n${c.cyan}${c.bold}StreamForge Status${c.reset}\n`);

  // ── API health ────────────────────────────────────────────────────────────
  process.stdout.write(`  ${c.dim}Checking API health...${c.reset}\r`);
  const health = await httpGet(config.api_url, '/health');
  console.log(`  ${statusIcon(health.ok)} API Health        ${health.ok ? `${c.green}Healthy${c.reset}` : `${c.red}Unhealthy${c.reset}`}  ${c.dim}(${config.api_url || 'not set'})${c.reset}`);

  // ── Pipelines ─────────────────────────────────────────────────────────────
  process.stdout.write(`  ${c.dim}Fetching pipelines...${c.reset}\r`);
  const pipelines = await httpGet(config.api_url, '/pipelines');
  const pipelineCount = pipelines.ok && Array.isArray(pipelines.body)
    ? pipelines.body.length
    : (pipelines.ok && pipelines.body && typeof pipelines.body.count === 'number')
      ? pipelines.body.count
      : null;
  console.log(`  ${statusIcon(pipelines.ok)} Pipelines         ${pipelineCount !== null ? c.bold + pipelineCount + c.reset : `${c.dim}unavailable${c.reset}`}`);

  // ── Event stats ───────────────────────────────────────────────────────────
  const analyticsBase = config.analytics_url || config.api_url;
  process.stdout.write(`  ${c.dim}Fetching event stats...${c.reset}\r`);
  const stats = await httpGet(analyticsBase, '/analytics/stats');
  if (stats.ok && typeof stats.body === 'object') {
    const s = stats.body;
    console.log(`  ${statusIcon(true)} Events Today      ${c.bold}${formatNumber(s.events_today ?? s.eventsToday ?? s.total)}${c.reset}`);
    console.log(`  ${statusIcon(true)} Events (24h)      ${c.bold}${formatNumber(s.events_24h ?? s.events24h ?? s.total)}${c.reset}`);
    if (s.throughput || s.events_per_sec) {
      console.log(`  ${statusIcon(true)} Throughput        ${c.bold}${formatNumber(s.throughput ?? s.events_per_sec)}${c.reset} events/sec`);
    }
  } else {
    console.log(`  ${statusIcon(false)} Event Stats       ${c.dim}unavailable${c.reset}`);
  }

  // ── Anomalies ─────────────────────────────────────────────────────────────
  process.stdout.write(`  ${c.dim}Checking anomalies...${c.reset}\r`);
  const anomalies = await httpGet(analyticsBase, '/analytics/anomalies');
  if (anomalies.ok && typeof anomalies.body === 'object') {
    const count = Array.isArray(anomalies.body)
      ? anomalies.body.length
      : (anomalies.body.count ?? anomalies.body.total ?? 0);
    const icon = count > 0 ? `${c.yellow}●${c.reset}` : `${c.green}●${c.reset}`;
    const label = count > 0 ? `${c.yellow}${c.bold}${count}${c.reset} ${c.yellow}detected${c.reset}` : `${c.green}None${c.reset}`;
    console.log(`  ${icon} Anomalies         ${label}`);
  } else {
    console.log(`  ${statusIcon(false)} Anomalies         ${c.dim}unavailable${c.reset}`);
  }

  // ── Config summary ────────────────────────────────────────────────────────
  console.log(`\n${c.bold}  Config${c.reset}`);
  console.log(`${c.dim}  ${'─'.repeat(45)}${c.reset}`);
  console.log(`  Org ID:           ${config.org_id || c.dim + 'not set' + c.reset}`);
  console.log(`  Default Pipeline: ${config.default_pipeline || c.dim + 'not set' + c.reset}`);
  console.log(`  API URL:          ${config.api_url || c.dim + 'not set' + c.reset}`);
  console.log(`  Analytics URL:    ${config.analytics_url || c.dim + 'not set' + c.reset}`);
  console.log('');
};
