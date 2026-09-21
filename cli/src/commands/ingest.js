/**
 * streamforge ingest <pipeline> <file>
 *
 * Reads a JSON or CSV file, then POSTs each event (or a batch) to the
 * pipeline's ingest endpoint.  Shows a progress indicator and summary.
 */

'use strict';

const fs    = require('fs');
const path  = require('path');
const http  = require('http');
const https = require('https');
const { loadConfig, c } = require('../config');

// ── CSV parser (minimal, handles quoted fields) ─────────────────────────────
function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];

  const headers = splitCsvLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const values = splitCsvLine(lines[i]);
    if (values.length === 0) continue;
    const obj = {};
    headers.forEach((h, idx) => {
      let val = values[idx] || '';
      // Auto-cast numbers and booleans
      if (/^-?\d+(\.\d+)?$/.test(val)) val = Number(val);
      else if (val === 'true') val = true;
      else if (val === 'false') val = false;
      obj[h] = val;
    });
    rows.push(obj);
  }
  return rows;
}

function splitCsvLine(line) {
  const fields = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') { current += '"'; i++; }
      else if (ch === '"') { inQuotes = false; }
      else { current += ch; }
    } else {
      if (ch === '"') { inQuotes = true; }
      else if (ch === ',') { fields.push(current.trim()); current = ''; }
      else { current += ch; }
    }
  }
  fields.push(current.trim());
  return fields;
}

// ── HTTP POST helper ────────────────────────────────────────────────────────
function postEvents(apiUrl, pipeline, events) {
  return new Promise((resolve) => {
    const endpoint = apiUrl.replace(/\/+$/, '') + '/pipelines/' + encodeURIComponent(pipeline) + '/events';
    const url = new URL(endpoint);
    const client = url.protocol === 'https:' ? https : http;

    const payload = JSON.stringify({ events });
    const options = {
      method:   'POST',
      hostname: url.hostname,
      port:     url.port || undefined,
      path:     url.pathname + url.search,
      headers: {
        'Content-Type':   'application/json',
        'Content-Length':  Buffer.byteLength(payload),
      },
      timeout: 30000,
    };

    const req = client.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => resolve({ ok: res.statusCode >= 200 && res.statusCode < 400, status: res.statusCode, body }));
    });

    req.on('timeout', () => { req.destroy(); resolve({ ok: false, status: 0, body: 'Request timed out' }); });
    req.on('error', (err) => resolve({ ok: false, status: 0, body: err.message }));

    req.write(payload);
    req.end();
  });
}

// ── progress bar ────────────────────────────────────────────────────────────
function progressBar(current, total, width) {
  width = width || 30;
  const pct   = Math.round((current / total) * 100);
  const filled = Math.round((current / total) * width);
  const bar   = '█'.repeat(filled) + '░'.repeat(width - filled);
  return `${bar} ${pct}% (${current}/${total})`;
}

// ── main ────────────────────────────────────────────────────────────────────
module.exports = async function ingest(argv) {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(`\n${c.bold}streamforge ingest <pipeline> <file>${c.reset}`);
    console.log(`\nRead a JSON or CSV file and send events to a pipeline.\n`);
    console.log(`${c.bold}ARGUMENTS${c.reset}`);
    console.log(`  pipeline   Name of the target pipeline`);
    console.log(`  file       Path to a .json or .csv file\n`);
    console.log(`${c.bold}OPTIONS${c.reset}`);
    console.log(`  ${c.yellow}--batch-size <n>${c.reset}   Events per request (default: 100)\n`);
    console.log(`${c.bold}EXAMPLES${c.reset}`);
    console.log(`  streamforge ingest my-pipeline ./data/events.json`);
    console.log(`  streamforge ingest clicks events.csv --batch-size 50\n`);
    return;
  }

  // Parse positional args (skip flags)
  const positional = argv.filter((a) => !a.startsWith('-'));
  const pipeline   = positional[0];
  const filePath   = positional[1];

  // --batch-size flag
  let batchSize = 100;
  const bsIdx = argv.indexOf('--batch-size');
  if (bsIdx !== -1 && argv[bsIdx + 1]) {
    batchSize = parseInt(argv[bsIdx + 1], 10) || 100;
  }

  if (!pipeline || !filePath) {
    console.error(`${c.red}Error: Both <pipeline> and <file> are required.${c.reset}`);
    console.error(`Usage: streamforge ingest <pipeline> <file>\n`);
    process.exit(1);
  }

  // Resolve file
  const resolved = path.resolve(filePath);
  if (!fs.existsSync(resolved)) {
    console.error(`${c.red}Error: File not found — ${resolved}${c.reset}`);
    process.exit(1);
  }

  const config = loadConfig({ required: true });
  if (!config.api_url) {
    console.error(`${c.red}Error: No API URL configured. Run ${c.cyan}streamforge connect <url>${c.red} first.${c.reset}`);
    process.exit(1);
  }

  console.log(`\n${c.cyan}${c.bold}StreamForge Ingest${c.reset}\n`);
  console.log(`  Pipeline:   ${c.bold}${pipeline}${c.reset}`);
  console.log(`  File:       ${c.bold}${resolved}${c.reset}`);
  console.log(`  Batch size: ${c.bold}${batchSize}${c.reset}\n`);

  // Read and parse file
  const ext = path.extname(resolved).toLowerCase();
  let events;

  try {
    const raw = fs.readFileSync(resolved, 'utf-8');
    if (ext === '.csv') {
      events = parseCsv(raw);
    } else if (ext === '.json') {
      const parsed = JSON.parse(raw);
      events = Array.isArray(parsed) ? parsed : [parsed];
    } else {
      console.error(`${c.red}Error: Unsupported file type "${ext}". Use .json or .csv.${c.reset}`);
      process.exit(1);
    }
  } catch (err) {
    console.error(`${c.red}Error parsing file: ${err.message}${c.reset}`);
    process.exit(1);
  }

  if (events.length === 0) {
    console.log(`${c.yellow}No events found in file.${c.reset}`);
    return;
  }

  console.log(`  Events:     ${c.bold}${events.length}${c.reset}\n`);

  // Send in batches
  const totalBatches = Math.ceil(events.length / batchSize);
  let sent    = 0;
  let failed  = 0;
  const start = Date.now();

  for (let i = 0; i < totalBatches; i++) {
    const batch = events.slice(i * batchSize, (i + 1) * batchSize);
    const result = await postEvents(config.api_url, pipeline, batch);

    if (result.ok) {
      sent += batch.length;
    } else {
      failed += batch.length;
      if (i === 0) {
        // Show error detail on first failure
        console.error(`  ${c.red}Batch 1 failed: HTTP ${result.status} — ${result.body}${c.reset}`);
      }
    }

    // Update progress
    const progress = progressBar(i + 1, totalBatches);
    process.stdout.write(`\r  ${c.dim}Progress:${c.reset} ${progress}`);
  }

  const elapsed = ((Date.now() - start) / 1000).toFixed(2);

  console.log('\n');
  console.log(`${c.bold}Results${c.reset}`);
  console.log(`${c.dim}${'─'.repeat(40)}${c.reset}`);
  console.log(`  ${c.green}Sent:${c.reset}    ${sent} events`);
  if (failed > 0) {
    console.log(`  ${c.red}Failed:${c.reset}  ${failed} events`);
  }
  console.log(`  ${c.dim}Time:    ${elapsed}s${c.reset}`);
  console.log(`${c.dim}${'─'.repeat(40)}${c.reset}\n`);

  if (failed > 0) {
    process.exit(1);
  }
};
