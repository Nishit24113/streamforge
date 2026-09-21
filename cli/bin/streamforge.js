#!/usr/bin/env node

/**
 * StreamForge CLI — entry point
 *
 * Usage:
 *   streamforge <command> [options]
 *
 * Commands:
 *   init                          Initialize StreamForge in the current project
 *   connect <api-url>             Connect to a StreamForge deployment
 *   status                        Show deployment health and stats
 *   ingest <pipeline> <file>      Send events from a JSON/CSV file
 *   deploy                        Deploy infrastructure via deploy.sh
 */

'use strict';

const path = require('path');

// ── ANSI helpers ────────────────────────────────────────────────────────────
const c = {
  reset:   '\x1b[0m',
  bold:    '\x1b[1m',
  dim:     '\x1b[2m',
  red:     '\x1b[31m',
  green:   '\x1b[32m',
  yellow:  '\x1b[33m',
  cyan:    '\x1b[36m',
  magenta: '\x1b[35m',
  white:   '\x1b[37m',
};

// ── Argument parsing ────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const command = args[0];

function printBanner() {
  console.log(`
${c.cyan}${c.bold}  ____  _                            _____                    ${c.reset}
${c.cyan}${c.bold} / ___|| |_ _ __ ___  __ _ _ __ ___ |  ___|__  _ __ __ _  ___ ${c.reset}
${c.cyan}${c.bold} \\___ \\| __| '__/ _ \\/ _\` | '_ \` _ \\| |_ / _ \\| '__/ _\` |/ _ \\${c.reset}
${c.cyan}${c.bold}  ___) | |_| | |  __/ (_| | | | | | |  _| (_) | | | (_| |  __/${c.reset}
${c.cyan}${c.bold} |____/ \\__|_|  \\___|\\__,_|_| |_| |_|_|  \\___/|_|  \\__, |\\___| ${c.reset}
${c.cyan}${c.bold}                                                    |___/      ${c.reset}
${c.dim}  Serverless Real-Time Data Pipeline Platform — CLI v1.0.0${c.reset}
`);
}

function printHelp() {
  printBanner();
  console.log(`${c.bold}USAGE${c.reset}`);
  console.log(`  streamforge <command> [options]\n`);
  console.log(`${c.bold}COMMANDS${c.reset}`);
  console.log(`  ${c.green}init${c.reset}                          Initialize StreamForge in the current project`);
  console.log(`  ${c.green}connect${c.reset} <api-url>             Connect to a StreamForge deployment`);
  console.log(`  ${c.green}status${c.reset}                        Show deployment health and stats`);
  console.log(`  ${c.green}ingest${c.reset}  <pipeline> <file>     Send events from a JSON/CSV file`);
  console.log(`  ${c.green}deploy${c.reset}                        Deploy infrastructure via deploy.sh\n`);
  console.log(`${c.bold}OPTIONS${c.reset}`);
  console.log(`  ${c.yellow}--help, -h${c.reset}                    Show this help message`);
  console.log(`  ${c.yellow}--version, -v${c.reset}                 Show version number\n`);
  console.log(`${c.bold}EXAMPLES${c.reset}`);
  console.log(`  ${c.dim}# Initialize in an existing project${c.reset}`);
  console.log(`  streamforge init\n`);
  console.log(`  ${c.dim}# Connect to a deployment${c.reset}`);
  console.log(`  streamforge connect https://abc.execute-api.us-west-2.amazonaws.com/v1\n`);
  console.log(`  ${c.dim}# Check status${c.reset}`);
  console.log(`  streamforge status\n`);
  console.log(`  ${c.dim}# Send test data${c.reset}`);
  console.log(`  streamforge ingest my-pipeline ./data/events.json\n`);
  console.log(`  ${c.dim}# Deploy infrastructure${c.reset}`);
  console.log(`  streamforge deploy --profile sandbox2025\n`);
}

// ── Route to command ────────────────────────────────────────────────────────
if (!command || command === '--help' || command === '-h') {
  printHelp();
  process.exit(0);
}

if (command === '--version' || command === '-v') {
  console.log('streamforge-cli v1.0.0');
  process.exit(0);
}

const commandsDir = path.join(__dirname, '..', 'src', 'commands');
const commandMap = {
  init:    'init',
  connect: 'connect',
  status:  'status',
  ingest:  'ingest',
  deploy:  'deploy',
};

const cmdFile = commandMap[command];
if (!cmdFile) {
  console.error(`${c.red}Unknown command: ${command}${c.reset}`);
  console.error(`Run ${c.cyan}streamforge --help${c.reset} for usage.\n`);
  process.exit(1);
}

const handler = require(path.join(commandsDir, cmdFile + '.js'));
handler(args.slice(1));
