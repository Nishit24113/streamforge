/**
 * Tests for the StreamForge CLI configuration module.
 *
 * Mocks fs to isolate file system access.
 * Run with: node --experimental-vm-modules node_modules/.bin/jest cli/test/config.test.js
 *           (or: npx jest cli/test/config.test.js)
 */

'use strict';

const path = require('path');
const fs   = require('fs');

// We need to require config fresh in some tests, so we capture the path.
const CONFIG_MODULE_PATH = require.resolve('../src/config');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function requireFreshConfig() {
  // Clear module cache to get a clean import
  delete require.cache[CONFIG_MODULE_PATH];
  return require(CONFIG_MODULE_PATH);
}

// ---------------------------------------------------------------------------
// loadConfig
// ---------------------------------------------------------------------------

describe('loadConfig', () => {
  let originalCwd;
  let originalEnv;

  beforeEach(() => {
    originalCwd = process.cwd;
    originalEnv = { ...process.env };
    // Clear relevant env vars
    delete process.env.STREAMFORGE_API_URL;
    delete process.env.STREAMFORGE_ANALYTICS_URL;
    delete process.env.STREAMFORGE_ORG_ID;
    delete process.env.STREAMFORGE_PIPELINE;
  });

  afterEach(() => {
    process.cwd = originalCwd;
    process.env = originalEnv;
    jest.restoreAllMocks();
  });

  it('reads .streamforge.json from cwd', () => {
    const fileConfig = {
      api_url: 'https://api.example.com',
      analytics_url: 'https://analytics.example.com',
      org_id: 'test-org',
      default_pipeline: 'my-events',
    };

    jest.spyOn(fs, 'existsSync').mockImplementation((p) => {
      return String(p).endsWith('.streamforge.json');
    });
    jest.spyOn(fs, 'readFileSync').mockReturnValue(JSON.stringify(fileConfig));

    const { loadConfig } = requireFreshConfig();
    const config = loadConfig();

    expect(config.api_url).toBe('https://api.example.com');
    expect(config.analytics_url).toBe('https://analytics.example.com');
    expect(config.org_id).toBe('test-org');
    expect(config.default_pipeline).toBe('my-events');
  });

  it('falls back to env vars when no config file exists', () => {
    jest.spyOn(fs, 'existsSync').mockReturnValue(false);

    process.env.STREAMFORGE_API_URL = 'https://env-api.example.com';
    process.env.STREAMFORGE_ANALYTICS_URL = 'https://env-analytics.example.com';
    process.env.STREAMFORGE_ORG_ID = 'env-org';
    process.env.STREAMFORGE_PIPELINE = 'env-pipeline';

    const { loadConfig } = requireFreshConfig();
    const config = loadConfig();

    expect(config.api_url).toBe('https://env-api.example.com');
    expect(config.analytics_url).toBe('https://env-analytics.example.com');
    expect(config.org_id).toBe('env-org');
    expect(config.default_pipeline).toBe('env-pipeline');
  });

  it('env vars override file values', () => {
    const fileConfig = {
      api_url: 'https://file-api.example.com',
      org_id: 'file-org',
    };

    jest.spyOn(fs, 'existsSync').mockImplementation((p) => {
      return String(p).endsWith('.streamforge.json');
    });
    jest.spyOn(fs, 'readFileSync').mockReturnValue(JSON.stringify(fileConfig));

    process.env.STREAMFORGE_API_URL = 'https://env-api.example.com';

    const { loadConfig } = requireFreshConfig();
    const config = loadConfig();

    // env var should win
    expect(config.api_url).toBe('https://env-api.example.com');
    // file value should be used when env is not set
    expect(config.org_id).toBe('file-org');
  });

  it('returns empty strings when nothing is configured', () => {
    jest.spyOn(fs, 'existsSync').mockReturnValue(false);

    const { loadConfig } = requireFreshConfig();
    const config = loadConfig();

    expect(config.api_url).toBe('');
    expect(config.analytics_url).toBe('');
    expect(config.org_id).toBe('');
    expect(config.default_pipeline).toBe('');
  });

  it('exits with error when required and no config found', () => {
    jest.spyOn(fs, 'existsSync').mockReturnValue(false);
    const mockExit = jest.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('process.exit');
    });
    jest.spyOn(console, 'error').mockImplementation(() => {});

    const { loadConfig } = requireFreshConfig();

    expect(() => loadConfig({ required: true })).toThrow('process.exit');
    expect(mockExit).toHaveBeenCalledWith(1);
  });

  it('handles malformed JSON gracefully', () => {
    jest.spyOn(fs, 'existsSync').mockImplementation((p) => {
      return String(p).endsWith('.streamforge.json');
    });
    jest.spyOn(fs, 'readFileSync').mockReturnValue('{ invalid json }');
    const mockExit = jest.spyOn(process, 'exit').mockImplementation(() => {
      throw new Error('process.exit');
    });
    jest.spyOn(console, 'error').mockImplementation(() => {});

    const { loadConfig } = requireFreshConfig();

    expect(() => loadConfig()).toThrow('process.exit');
    expect(mockExit).toHaveBeenCalledWith(1);
  });
});

// ---------------------------------------------------------------------------
// saveConfig
// ---------------------------------------------------------------------------

describe('saveConfig', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('writes correct JSON to .streamforge.json', () => {
    const writeSpy = jest.spyOn(fs, 'writeFileSync').mockImplementation(() => {});

    const { saveConfig } = requireFreshConfig();

    const config = {
      api_url: 'https://api.example.com',
      org_id: 'my-org',
      default_pipeline: 'events',
    };

    const targetDir = '/home/user/project';
    const savedPath = saveConfig(config, targetDir);

    expect(writeSpy).toHaveBeenCalledTimes(1);
    const [filePath, content, encoding] = writeSpy.mock.calls[0];

    expect(filePath).toBe(path.join(targetDir, '.streamforge.json'));
    expect(encoding).toBe('utf-8');

    const parsed = JSON.parse(content);
    expect(parsed.api_url).toBe('https://api.example.com');
    expect(parsed.org_id).toBe('my-org');
    expect(parsed.default_pipeline).toBe('events');
  });

  it('formats JSON with 2-space indentation and trailing newline', () => {
    const writeSpy = jest.spyOn(fs, 'writeFileSync').mockImplementation(() => {});

    const { saveConfig } = requireFreshConfig();
    saveConfig({ api_url: 'https://x.com' }, '/tmp');

    const content = writeSpy.mock.calls[0][1];
    // Should have 2-space indent
    expect(content).toContain('  "api_url"');
    // Should end with newline
    expect(content.endsWith('\n')).toBe(true);
  });

  it('returns the saved file path', () => {
    jest.spyOn(fs, 'writeFileSync').mockImplementation(() => {});

    const { saveConfig } = requireFreshConfig();
    const result = saveConfig({ api_url: 'https://x.com' }, '/my/dir');

    expect(result).toBe(path.join('/my/dir', '.streamforge.json'));
  });
});

// ---------------------------------------------------------------------------
// findConfigPath
// ---------------------------------------------------------------------------

describe('findConfigPath', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('returns path when .streamforge.json exists in cwd', () => {
    const targetDir = path.resolve('/home/user/project');
    jest.spyOn(fs, 'existsSync').mockImplementation((p) => {
      return p === path.join(targetDir, '.streamforge.json');
    });

    const { findConfigPath } = requireFreshConfig();
    const result = findConfigPath(targetDir);

    expect(result).toBe(path.join(targetDir, '.streamforge.json'));
  });

  it('walks up directories to find config', () => {
    const rootDir = path.resolve('/home/user/project');
    const subDir = path.join(rootDir, 'src', 'lib');

    jest.spyOn(fs, 'existsSync').mockImplementation((p) => {
      return p === path.join(rootDir, '.streamforge.json');
    });

    const { findConfigPath } = requireFreshConfig();
    const result = findConfigPath(subDir);

    expect(result).toBe(path.join(rootDir, '.streamforge.json'));
  });

  it('returns null when no config found anywhere', () => {
    jest.spyOn(fs, 'existsSync').mockReturnValue(false);

    const { findConfigPath } = requireFreshConfig();
    const result = findConfigPath('/some/path');

    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// CONFIG_FILE constant
// ---------------------------------------------------------------------------

describe('CONFIG_FILE', () => {
  it('is .streamforge.json', () => {
    const { CONFIG_FILE } = requireFreshConfig();
    expect(CONFIG_FILE).toBe('.streamforge.json');
  });
});
