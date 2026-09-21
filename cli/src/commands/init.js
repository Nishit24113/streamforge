/**
 * streamforge init
 *
 * Interactive project initializer:
 *   - Asks for API URL (or reads STREAMFORGE_API_URL)
 *   - Asks for pipeline name
 *   - Detects project type (Node / Python) and offers to install the SDK
 *   - Writes .streamforge.json
 *   - Prints a quickstart snippet
 */

'use strict';

const fs       = require('fs');
const path     = require('path');
const readline = require('readline');
const { execSync } = require('child_process');
const { saveConfig, CONFIG_FILE, c } = require('../config');

// ── tiny prompt helper ──────────────────────────────────────────────────────
function ask(rl, question, fallback) {
  return new Promise((resolve) => {
    const suffix = fallback ? ` ${c.dim}(${fallback})${c.reset}` : '';
    rl.question(`${c.cyan}?${c.reset} ${question}${suffix}: `, (answer) => {
      resolve(answer.trim() || fallback || '');
    });
  });
}

// ── project-type detection ──────────────────────────────────────────────────
function detectProjectType(cwd) {
  if (fs.existsSync(path.join(cwd, 'package.json')))      return 'node';
  if (fs.existsSync(path.join(cwd, 'requirements.txt')))  return 'python';
  if (fs.existsSync(path.join(cwd, 'pyproject.toml')))    return 'python';
  if (fs.existsSync(path.join(cwd, 'setup.py')))          return 'python';
  return null;
}

// ── quickstart snippets ─────────────────────────────────────────────────────
function nodeSnippet(apiUrl, pipeline) {
  return `
${c.bold}// quickstart.js${c.reset}
const http = require('https');

const API_URL = '${apiUrl}';
const PIPELINE = '${pipeline}';

const event = {
  user_id: 'u-123',
  action: 'page_view',
  page: '/home',
  ts: new Date().toISOString(),
};

const url = new URL(\`\${API_URL}/pipelines/\${PIPELINE}/events\`);
const options = {
  method: 'POST',
  hostname: url.hostname,
  path: url.pathname,
  headers: { 'Content-Type': 'application/json' },
};

const req = http.request(options, (res) => {
  let body = '';
  res.on('data', (chunk) => body += chunk);
  res.on('end', () => console.log('Response:', body));
});
req.write(JSON.stringify(event));
req.end();
`;
}

function pythonSnippet(apiUrl, pipeline) {
  return `
${c.bold}# quickstart.py${c.reset}
import requests, datetime, json

API_URL = "${apiUrl}"
PIPELINE = "${pipeline}"

event = {
    "user_id": "u-123",
    "action": "page_view",
    "page": "/home",
    "ts": datetime.datetime.utcnow().isoformat() + "Z",
}

resp = requests.post(
    f"{API_URL}/pipelines/{PIPELINE}/events",
    json=event,
)
print("Response:", resp.status_code, resp.text)
`;
}

// ── main ────────────────────────────────────────────────────────────────────
module.exports = async function init(argv) {
  const cwd = process.cwd();

  // Check for --help
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(`\n${c.bold}streamforge init${c.reset}`);
    console.log(`\nInitialize StreamForge in the current project.\n`);
    console.log(`Creates ${c.cyan}${CONFIG_FILE}${c.reset} and optionally installs the SDK.\n`);
    return;
  }

  console.log(`\n${c.cyan}${c.bold}StreamForge Init${c.reset}\n`);

  // Warn if config already exists
  const existingConfig = path.join(cwd, CONFIG_FILE);
  if (fs.existsSync(existingConfig)) {
    console.log(`${c.yellow}Warning:${c.reset} ${CONFIG_FILE} already exists in this directory.`);
    console.log(`${c.dim}Continuing will overwrite the existing config.${c.reset}\n`);
  }

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  try {
    // 1. API URL
    const envUrl = process.env.STREAMFORGE_API_URL || '';
    const apiUrl = await ask(rl, 'API URL', envUrl || 'https://xxx.execute-api.us-west-2.amazonaws.com/v1');

    // 2. Analytics URL (optional)
    const analyticsUrl = await ask(rl, 'Analytics URL (optional)', '');

    // 3. Org ID
    const orgId = await ask(rl, 'Organization ID', 'my-org');

    // 4. Default pipeline
    const pipeline = await ask(rl, 'Default pipeline name', 'my-events');

    // 5. Detect project type
    const projectType = detectProjectType(cwd);
    let installSdk = false;

    if (projectType) {
      const sdkName = projectType === 'node' ? 'streamforge (npm)' : 'streamforge (pip)';
      const answer = await ask(rl, `Detected ${c.green}${projectType}${c.reset} project. Install ${sdkName}?`, 'y/N');
      installSdk = answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes';
    }

    rl.close();

    // 6. Write config
    const config = {
      api_url:          apiUrl,
      analytics_url:    analyticsUrl || undefined,
      org_id:           orgId,
      default_pipeline: pipeline,
    };
    // Remove undefined keys for clean JSON
    Object.keys(config).forEach((k) => { if (config[k] === undefined) delete config[k]; });

    const savedPath = saveConfig(config, cwd);
    console.log(`\n${c.green}Created${c.reset} ${savedPath}`);

    // 7. Install SDK
    if (installSdk) {
      console.log(`\n${c.cyan}Installing SDK...${c.reset}`);
      try {
        if (projectType === 'node') {
          execSync('npm install streamforge --save', { cwd, stdio: 'inherit' });
        } else {
          execSync('pip install streamforge', { cwd, stdio: 'inherit' });
        }
        console.log(`${c.green}SDK installed successfully.${c.reset}`);
      } catch {
        console.log(`${c.yellow}SDK install failed — you can install it manually later.${c.reset}`);
      }
    }

    // 8. Quickstart snippet
    console.log(`\n${c.bold}Quickstart${c.reset}`);
    console.log(`${c.dim}${'─'.repeat(60)}${c.reset}`);
    if (projectType === 'python') {
      console.log(pythonSnippet(apiUrl, pipeline));
    } else {
      console.log(nodeSnippet(apiUrl, pipeline));
    }
    console.log(`${c.dim}${'─'.repeat(60)}${c.reset}`);

    console.log(`\n${c.green}${c.bold}StreamForge initialized!${c.reset}`);
    console.log(`Run ${c.cyan}streamforge status${c.reset} to verify the connection.\n`);
  } catch (err) {
    rl.close();
    console.error(`${c.red}Init failed: ${err.message}${c.reset}`);
    process.exit(1);
  }
};
