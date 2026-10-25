/**
 * components/header.js
 * ====================
 * Header bar, navigation tabs, persistent DEMO MODE — SIMULATED DATA indicator, demo reset, and settings.
 */

import { CONFIG, setDemoMode, setTheme, setApiBaseUrl } from '../config.js';
import { escapeHTML } from '../security.js';

export function renderHeader(state) {
  const isDemo = state.isDemoData || CONFIG.DEMO_MODE;
  const activeTab = state.activeTab;

  return `
    <header class="top-header" role="banner">
      <div class="header-inner container">
        <div class="brand-group">
          <div class="logo-mark">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z"/>
              <path d="M9 12l2 2 4-4"/>
            </svg>
          </div>
          <div>
            <h1 class="brand-title">Veritas Gate</h1>
            <span class="brand-subtitle">Deterministic Governance Verdict Engine</span>
          </div>
        </div>

        <nav class="nav-tabs" role="navigation" aria-label="Main Navigation">
          <button class="nav-tab ${activeTab === 'overview' ? 'active' : ''}" data-tab="overview">
            Overview
          </button>
          <button class="nav-tab ${activeTab === 'explorer' ? 'active' : ''}" data-tab="explorer">
            Proposal Explorer
          </button>
          <button class="nav-tab ${activeTab === 'detail' ? 'active' : ''}" data-tab="detail">
            Proposal Analysis
          </button>
          <button class="nav-tab ${activeTab === 'reviewer' ? 'active' : ''}" data-tab="reviewer">
            Reviewer Queue
            ${state.proposals.filter(p => p.verdict?.status === 'NEEDS_REVIEW').length > 0 ? 
              `<span class="tab-badge">${state.proposals.filter(p => p.verdict?.status === 'NEEDS_REVIEW').length}</span>` : ''}
          </button>
          <button class="nav-tab ${activeTab === 'challenges' ? 'active' : ''}" data-tab="challenges">
            Challenges &amp; Guardian
          </button>
          <button class="nav-tab ${activeTab === 'redteam' ? 'active' : ''}" data-tab="redteam">
            Red Team Arena
          </button>
        </nav>

        <div class="header-actions">
          <div class="env-pill ${isDemo ? 'env-demo' : 'env-live'}" title="${isDemo ? 'Demo Mode: Offline execution with simulated test fixtures' : 'Live Mode connected to API at ' + escapeHTML(CONFIG.API_BASE_URL)}">
            <span class="status-dot"></span>
            <span>${isDemo ? 'DEMO MODE — SIMULATED DATA' : 'LIVE API'}</span>
          </div>

          ${isDemo ? `
            <button id="reset-demo-btn" class="btn btn-sm btn-outline" title="Reset all demo interactions, reviews, and votes back to pristine state">
              Reset Demo
            </button>
          ` : ''}

          <button id="toggle-demo-btn" class="btn btn-sm ${isDemo ? 'btn-warning' : 'btn-outline'}" 
                  title="${isDemo ? 'Disable Demo Mode and connect to Live API' : 'Enable Demo Mode with labelled synthetic fixtures'}">
            ${isDemo ? 'Disable Demo' : 'Enable Demo Mode'}
          </button>

          <button id="refresh-btn" class="btn btn-sm btn-icon" title="Refresh Data" aria-label="Refresh Data">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M23 4v6h-6M1 20v-6h6"/>
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
          </button>

          <button id="theme-btn" class="btn btn-sm btn-icon" title="Toggle Theme" aria-label="Toggle Dark/Light Theme">
            ${CONFIG.THEME === 'dark' ? 
              `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>` : 
              `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`}
          </button>

          <button id="settings-btn" class="btn btn-sm btn-icon" title="API Settings" aria-label="API Settings">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>

      ${isDemo ? `
        <div class="demo-banner" role="alert">
          <div class="container demo-banner-content">
            <span class="demo-badge">DEMO MODE — SIMULATED DATA</span>
            <span>Offline educational simulation harness. Seeded proposals, bytecode diffs, and review decisions are simulated demonstration fixtures. No live blockchain, real wallets, or transactions required.</span>
          </div>
        </div>
      ` : ''}
    </header>
  `;
}
