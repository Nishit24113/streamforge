/**
 * StreamForge CLI — Configuration loader
 *
 * Reads .streamforge.json from the current working directory and merges
 * with environment variables.  Env vars take precedence over file values.
 */

const fs   = require('fs');
const path = require('path');

const CONFIG_FILE = '.streamforge.json';

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

/**
 * Resolve the config file path — walks up from `cwd` to the filesystem root
 * so the CLI works from any sub-directory of the project.
 */
function findConfigPath(cwd) {
  let dir = path.resolve(cwd || process.cwd());
  while (true) {
    const candidate = path.join(dir, CONFIG_FILE);
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) return null;   // reached root
    dir = parent;
  }
}

/**
 * Load and return the merged config object.
 *
 * @param {object} opts
 * @param {boolean} opts.required  — if true, exit with error when no config found
 * @returns {object}
 */
function loadConfig(opts = {}) {
  const configPath = findConfigPath();
  let fileConfig = {};

  if (configPath) {
    try {
      const raw = fs.readFileSync(configPath, 'utf-8');
      fileConfig = JSON.parse(raw);
    } catch (err) {
      console.error(`${c.red}Error reading ${configPath}: ${err.message}${c.reset}`);
      process.exit(1);
    }
  } else if (opts.required) {
    console.error(
      `${c.red}No ${CONFIG_FILE} found.${c.reset}\n` +
      `Run ${c.cyan}streamforge init${c.reset} or ${c.cyan}streamforge connect <api-url>${c.reset} first.`
    );
    process.exit(1);
  }

  // Env-var overrides
  return {
    api_url:          process.env.STREAMFORGE_API_URL       || fileConfig.api_url          || '',
    analytics_url:    process.env.STREAMFORGE_ANALYTICS_URL || fileConfig.analytics_url    || '',
    org_id:           process.env.STREAMFORGE_ORG_ID        || fileConfig.org_id           || '',
    default_pipeline: process.env.STREAMFORGE_PIPELINE      || fileConfig.default_pipeline || '',
  };
}

/**
 * Write a config object to .streamforge.json in the current working directory.
 */
function saveConfig(config, dir) {
  const target = path.join(dir || process.cwd(), CONFIG_FILE);
  fs.writeFileSync(target, JSON.stringify(config, null, 2) + '\n', 'utf-8');
  return target;
}

module.exports = { loadConfig, saveConfig, findConfigPath, CONFIG_FILE, c };
