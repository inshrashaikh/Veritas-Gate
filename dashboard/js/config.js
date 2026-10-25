/**
 * config.js
 * =========
 * Application configuration, storage keys, and environment settings.
 * 
 * Rules:
 * - Real API configuration; no hardcoded assumptions.
 * - Demo mode disabled by default.
 * - Zero secrets or private keys.
 */

const STORAGE_KEYS = {
  API_URL: 'veritas_gate_api_url',
  DEMO_MODE: 'veritas_gate_demo_mode',
  THEME: 'veritas_gate_theme',
  ACTIVE_PROPOSAL: 'veritas_gate_active_proposal'
};

function safeGetStorage(key, fallback = null) {
  try {
    if (typeof localStorage !== 'undefined') {
      const val = localStorage.getItem(key);
      return val !== null ? val : fallback;
    }
  } catch (_) {}
  return fallback;
}

function safeSetStorage(key, val) {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(key, String(val));
    }
  } catch (_) {}
}

export const CONFIG = {
  // Configurable base URL; defaults to local backend at port 5000
  API_BASE_URL: (() => {
    const val = safeGetStorage(STORAGE_KEYS.API_URL);
    return (!val || val.includes(':8000')) ? 'http://127.0.0.1:5000' : val;
  })(),
  
  // FAIL-CLOSED / SAFETY RULE: Demo mode is strictly disabled by default
  DEMO_MODE: safeGetStorage(STORAGE_KEYS.DEMO_MODE, 'false') === 'true',
  
  THEME: safeGetStorage(STORAGE_KEYS.THEME, 'dark'),
  
  REFRESH_INTERVAL_MS: 30000,
  REQUEST_TIMEOUT_MS: 3000,
  
  VERDICT_CLASSES: {
    VERIFIED: 'verdict-verified',
    MISMATCH: 'verdict-mismatch',
    NEEDS_REVIEW: 'verdict-needs-review'
  },
  
  SEVERITY_LEVELS: {
    CRITICAL: 'badge-danger',
    HIGH: 'badge-warning',
    MEDIUM: 'badge-info',
    LOW: 'badge-neutral'
  }
};

export function setApiBaseUrl(newUrl) {
  if (typeof newUrl === 'string') {
    const trimmed = newUrl.trim();
    CONFIG.API_BASE_URL = trimmed;
    safeSetStorage(STORAGE_KEYS.API_URL, trimmed);
  }
}

export function setDemoMode(enabled) {
  CONFIG.DEMO_MODE = Boolean(enabled);
  safeSetStorage(STORAGE_KEYS.DEMO_MODE, CONFIG.DEMO_MODE);
}

export function setTheme(theme) {
  CONFIG.THEME = theme === 'light' ? 'light' : 'dark';
  safeSetStorage(STORAGE_KEYS.THEME, CONFIG.THEME);
  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.setAttribute('data-theme', CONFIG.THEME);
  }
}
