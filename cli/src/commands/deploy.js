/**
 * streamforge deploy
 *
 * Wraps the project's deploy.sh script.
 * Accepts --profile, --region, --mode flags and forwards them.
 */

'use strict';

const path = require('path');
const fs   = require('fs');
const { spawn } = require('child_process');
const { findConfigPath, c } = require('../config');

// ── flag parser ─────────────────────────────────────────────────────────────
function parseFlags(argv) {
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--profile' && argv[i + 1])  { flags.profile = argv[++i]; }
    else if (argv[i] === '--region' && argv[i + 1])   { flags.region  = argv[++i]; }
    else if (argv[i] === '--mode' && argv[i + 1])     { flags.mode    = argv[++i]; }
    else if (argv[i] === '--dry-run')                  { flags.dryRun  = true; }
    else if (argv[i] === '--help' || argv[i] === '-h') { flags.help    = true; }
  }
  return flags;
}

// ── locate deploy.sh ────────────────────────────────────────────────────────
function findDeployScript() {
  // Walk up from config file or cwd to find deploy.sh
  const configPath = findConfigPath();
  const startDir   = configPath ? path.dirname(configPath) : process.cwd();

  let dir = startDir;
  while (true) {
    const candidate = path.join(dir, 'deploy.sh');
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

// ── main ────────────────────────────────────────────────────────────────────
module.exports = async function deploy(argv) {
  const flags = parseFlags(argv);

  if (flags.help) {
    console.log(`\n${c.bold}streamforge deploy${c.reset}`);
    console.log(`\nDeploy StreamForge infrastructure via deploy.sh.\n`);
    console.log(`${c.bold}OPTIONS${c.reset}`);
    console.log(`  ${c.yellow}--profile <name>${c.reset}   AWS profile to use`);
    console.log(`  ${c.yellow}--region  <name>${c.reset}   AWS region (e.g. us-west-2)`);
    console.log(`  ${c.yellow}--mode    <mode>${c.reset}   Deployment mode (e.g. full, update)`);
    console.log(`  ${c.yellow}--dry-run${c.reset}          Show what would be run without executing\n`);
    console.log(`${c.bold}EXAMPLES${c.reset}`);
    console.log(`  streamforge deploy`);
    console.log(`  streamforge deploy --profile sandbox2025`);
    console.log(`  streamforge deploy --profile prod --region us-east-1 --mode full\n`);
    return;
  }

  console.log(`\n${c.cyan}${c.bold}StreamForge Deploy${c.reset}\n`);

  const deployScript = findDeployScript();
  if (!deployScript) {
    console.error(`${c.red}Error: deploy.sh not found.${c.reset}`);
    console.error(`Make sure you are inside a StreamForge project directory.\n`);
    process.exit(1);
  }

  console.log(`  Script:  ${c.bold}${deployScript}${c.reset}`);
  if (flags.profile) console.log(`  Profile: ${c.bold}${flags.profile}${c.reset}`);
  if (flags.region)  console.log(`  Region:  ${c.bold}${flags.region}${c.reset}`);
  if (flags.mode)    console.log(`  Mode:    ${c.bold}${flags.mode}${c.reset}`);
  console.log('');

  // Build deploy.sh arguments
  const scriptArgs = [];
  if (flags.profile) scriptArgs.push('--profile', flags.profile);
  if (flags.region)  scriptArgs.push('--region',  flags.region);
  if (flags.mode)    scriptArgs.push('--mode',    flags.mode);

  if (flags.dryRun) {
    console.log(`${c.yellow}Dry run — would execute:${c.reset}`);
    console.log(`  bash ${deployScript} ${scriptArgs.join(' ')}\n`);
    return;
  }

  console.log(`${c.dim}Running deploy.sh...${c.reset}\n`);

  // Determine shell: use bash on all platforms. On Windows Git Bash provides it.
  const shell = process.platform === 'win32' ? 'bash' : '/bin/bash';

  return new Promise((resolve) => {
    const child = spawn(shell, [deployScript, ...scriptArgs], {
      cwd:   path.dirname(deployScript),
      stdio: 'inherit',
      env:   { ...process.env },
    });

    child.on('close', (code) => {
      console.log('');
      if (code === 0) {
        console.log(`${c.green}${c.bold}Deploy completed successfully.${c.reset}\n`);
      } else {
        console.log(`${c.red}Deploy failed with exit code ${code}.${c.reset}\n`);
        process.exit(code || 1);
      }
      resolve();
    });

    child.on('error', (err) => {
      console.error(`${c.red}Failed to run deploy.sh: ${err.message}${c.reset}`);
      if (process.platform === 'win32' && err.code === 'ENOENT') {
        console.error(`${c.yellow}Hint: Make sure Git Bash is installed and "bash" is on your PATH.${c.reset}`);
      }
      process.exit(1);
    });
  });
};
