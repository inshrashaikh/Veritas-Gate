/**
 * app.js
 * ======
 * Main Application Controller for Veritas Gate Phase 6 Dashboard.
 * 
 * Rules:
 * - Wires state management, API loading, and component rendering.
 * - Manages tab switching, search, filters, reviewer actions, and informed voting.
 * - STRICT: Enforces mandatory written reason for reviewer queue.
 * - STRICT: Enforces acknowledgement checkbox before voting.
 */

import { CONFIG, setDemoMode, setTheme, setApiBaseUrl } from './config.js';
import { api } from './api.js';
import { store } from './state.js';
import { renderHeader } from './components/header.js';
import { renderOverview } from './components/overview.js';
import { renderProposalExplorer } from './components/proposalExplorer.js';
import { renderVerdictCard } from './components/verdictCard.js';
import { renderEffectsDiff } from './components/effectsDiff.js';
import { renderEvaluationChain } from './components/evaluationChain.js';
import { renderEvidenceExplorer } from './components/evidenceExplorer.js';
import { renderReviewerQueue } from './components/reviewerQueue.js';
import { renderVotingPanel } from './components/votingPanel.js';
import { renderCoiPanel } from './components/coiPanel.js';
import { renderGuardianPanel } from './components/guardianPanel.js';
import { renderRedTeamArena } from './components/redTeamArena.js';
import { escapeHTML, truncateAddress } from './security.js';

class App {
  constructor() {
    this.appElement = document.getElementById('app');
    this.modalElement = document.getElementById('settings-modal');
  }

  async init() {
    // Apply saved theme
    setTheme(CONFIG.THEME);

    // Subscribe to state changes
    store.subscribe(() => this.render());

    // Initial data fetch
    await this.fetchData();
  }

  async fetchData() {
    store.setLoading(true);
    store.setError(null);

    try {
      // Parallel loading of available datasets
      const [metricsRes, proposalsRes, redTeamRes, challengesRes, guardianRes] = await Promise.allSettled([
        api.fetchMetrics(),
        api.fetchProposals(),
        api.fetchRedTeamArena(),
        api.fetchChallenges(),
        api.fetchGuardianEvents()
      ]);

      if (metricsRes.status === 'fulfilled') {
        store.setMetrics(metricsRes.value.data);
        store.setDemoData(metricsRes.value.isDemo);
      }
      if (proposalsRes.status === 'fulfilled') {
        store.setProposals(proposalsRes.value.data);
      }
      if (redTeamRes.status === 'fulfilled') {
        store.setRedTeamData(redTeamRes.value.data);
      }
      if (challengesRes.status === 'fulfilled') {
        store.setChallenges(challengesRes.value.data);
      }
      if (guardianRes.status === 'fulfilled') {
        store.setGuardianEvents(guardianRes.value.data);
      }

      // If requests failed and demo mode is off, record error
      if (!CONFIG.DEMO_MODE && (metricsRes.status === 'rejected' || proposalsRes.status === 'rejected')) {
        const errMsg = (metricsRes.status === 'rejected' ? metricsRes.reason?.message : null) ||
                       (proposalsRes.status === 'rejected' ? proposalsRes.reason?.message : null) ||
                       'Failed to connect to Veritas Gate API';
        store.setError(errMsg);
      }
    } catch (err) {
      store.setError(err.message || 'Unexpected connection error');
    } finally {
      store.setLoading(false);
    }
  }

  render() {
    const state = store.state;
    if (!this.appElement) return;

    let mainContentHtml = '';

    if (state.activeTab === 'overview') {
      mainContentHtml = renderOverview(state);
    } else if (state.activeTab === 'explorer') {
      mainContentHtml = renderProposalExplorer(state);
    } else if (state.activeTab === 'detail') {
      const selected = state.selectedProposal;
      if (!selected) {
        mainContentHtml = `
          <div class="card empty-state-card">
            <h3>No Proposal Selected</h3>
            <p class="text-muted">Select a proposal from the Proposal Explorer to inspect simulation traces and verdicts.</p>
            <button class="btn btn-sm btn-primary" onclick="window.app.setTab('explorer')">Go to Explorer</button>
          </div>
        `;
      } else {
        mainContentHtml = `
          <section class="detail-section" aria-labelledby="detail-heading">
            <div class="detail-nav-bar">
              <button class="btn btn-sm btn-outline" onclick="window.app.setTab('explorer')">
                ← Back to Explorer
              </button>
              <div class="detail-quick-meta">
                <span>Inspecting: <strong>${escapeHTML(selected.id)}</strong> (${escapeHTML(selected.version || 'v1.0')})</span>
                <span>Proposer: <code>${truncateAddress(selected.proposer)}</code></span>
              </div>
            </div>

            <!-- 1. Verdict Card -->
            ${renderVerdictCard(selected)}

            <!-- 2. Promises vs Actual Effects -->
            ${renderEffectsDiff(selected)}

            <!-- 3. Four-Stage Evaluation Chain -->
            ${renderEvaluationChain(selected)}

            <!-- 4. Split: Informed Voting & Conflict of Interest -->
            <div class="detail-split-grid">
              ${renderVotingPanel(selected, state.isDemoData)}
              ${renderCoiPanel(selected)}
            </div>

            <!-- 5. Evidence Explorer & Chronological Audit Timeline -->
            ${renderEvidenceExplorer(selected)}
          </section>
        `;
      }
    } else if (state.activeTab === 'reviewer') {
      mainContentHtml = renderReviewerQueue(state);
    } else if (state.activeTab === 'challenges') {
      mainContentHtml = renderGuardianPanel(state);
    } else if (state.activeTab === 'redteam') {
      mainContentHtml = renderRedTeamArena(state);
    }

    this.appElement.innerHTML = `
      ${renderHeader(state)}
      <main class="main-content container" role="main">
        ${mainContentHtml}
      </main>
      ${this.renderFooter(state)}
      ${this.renderSettingsModal()}
    `;

    this.bindEvents();
  }

  renderFooter(state) {
    return `
      <footer class="app-footer" role="contentinfo">
        <div class="container footer-inner">
          <div>
            <strong>Veritas Gate</strong> — Phase 6 Governance Dashboard
            <span class="text-muted text-xs"> (Fail-Closed Deterministic Architecture)</span>
          </div>
          <div class="footer-links text-xs text-muted">
            <span>Schema: <code>veritas-claims-v1.0</code> &amp; <code>veritas-simulation-v1.0</code></span>
            <span>API: <code>${escapeHTML(CONFIG.API_BASE_URL)}</code></span>
          </div>
        </div>
      </footer>
    `;
  }

  renderSettingsModal() {
    return `
      <div id="settings-modal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div class="modal-dialog card">
          <div class="modal-header">
            <h3 id="settings-title" class="modal-title">API &amp; Environment Settings</h3>
            <button class="btn btn-sm btn-icon close-modal-btn" aria-label="Close Settings">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label for="api-url-input" class="form-label font-bold">API Base URL</label>
              <input type="text" id="api-url-input" class="input" value="${escapeHTML(CONFIG.API_BASE_URL)}">
              <span class="text-muted text-xs">Default: <code>http://localhost:8000/api/v1</code></span>
            </div>
            <div class="form-group">
              <label class="checkbox-label" for="modal-demo-toggle">
                <input type="checkbox" id="modal-demo-toggle" class="checkbox" ${CONFIG.DEMO_MODE ? 'checked' : ''}>
                <span class="checkbox-text font-bold">Enable Demo Mode</span>
              </label>
              <span class="text-muted text-xs">Uses isolated educational fixtures from Phase 1 &amp; Phase 3 test cases.</span>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-sm btn-outline close-modal-btn">Cancel</button>
            <button id="save-settings-btn" class="btn btn-sm btn-primary">Save &amp; Reload</button>
          </div>
        </div>
      </div>
    `;
  }

  bindEvents() {
    // Navigation Tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', (e) => {
        const targetTab = e.currentTarget.getAttribute('data-tab');
        if (targetTab) store.setActiveTab(targetTab);
      });
    });

    // Theme toggle
    const themeBtn = document.getElementById('theme-btn');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => {
        const next = CONFIG.THEME === 'dark' ? 'light' : 'dark';
        setTheme(next);
        this.render();
      });
    }

    // Demo Mode toggle
    const toggleDemoBtn = document.getElementById('toggle-demo-btn');
    if (toggleDemoBtn) {
      toggleDemoBtn.addEventListener('click', async () => {
        setDemoMode(!CONFIG.DEMO_MODE);
        await this.fetchData();
      });
    }

    // Refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', async () => {
        await this.fetchData();
      });
    }

    // Settings Modal
    const settingsBtn = document.getElementById('settings-btn');
    const modal = document.getElementById('settings-modal');
    if (settingsBtn && modal) {
      settingsBtn.addEventListener('click', () => modal.classList.remove('hidden'));
      modal.querySelectorAll('.close-modal-btn').forEach(b => {
        b.addEventListener('click', () => modal.classList.add('hidden'));
      });
    }

    const saveSettingsBtn = document.getElementById('save-settings-btn');
    if (saveSettingsBtn) {
      saveSettingsBtn.addEventListener('click', async () => {
        const urlInput = document.getElementById('api-url-input');
        const demoToggle = document.getElementById('modal-demo-toggle');
        if (urlInput) setApiBaseUrl(urlInput.value);
        if (demoToggle) setDemoMode(demoToggle.checked);
        if (modal) modal.classList.add('hidden');
        await this.fetchData();
      });
    }

    // Proposal search & filters
    const searchInput = document.getElementById('proposal-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        store.setFilters({ searchQuery: e.target.value });
      });
    }

    const verdictFilter = document.getElementById('verdict-filter');
    if (verdictFilter) {
      verdictFilter.addEventListener('change', (e) => {
        store.setFilters({ verdict: e.target.value });
      });
    }

    const statusFilter = document.getElementById('status-filter');
    if (statusFilter) {
      statusFilter.addEventListener('change', (e) => {
        store.setFilters({ status: e.target.value });
      });
    }

    const sortFilter = document.getElementById('sort-filter');
    if (sortFilter) {
      sortFilter.addEventListener('change', (e) => {
        store.setFilters({ sortBy: e.target.value });
      });
    }

    const resetFiltersBtn = document.getElementById('reset-filters-btn');
    if (resetFiltersBtn) {
      resetFiltersBtn.addEventListener('click', () => {
        store.setFilters({ searchQuery: '', verdict: 'ALL', status: 'ALL', sortBy: 'date_desc' });
      });
    }

    // Inspect proposal buttons
    document.querySelectorAll('.select-proposal-btn, .table-row').forEach(el => {
      el.addEventListener('click', (e) => {
        const id = el.getAttribute('data-id') || el.closest('[data-id]')?.getAttribute('data-id');
        if (id) {
          store.selectProposalById(id);
          store.setActiveTab('detail');
        }
      });
    });

    // Reviewer Queue actions: Reason validation
    document.querySelectorAll('.reviewer-reason-input').forEach(textarea => {
      textarea.addEventListener('input', (e) => {
        const propId = e.target.getAttribute('data-id');
        const length = e.target.value.trim().length;
        const counter = document.getElementById(`counter-${propId}`);
        if (counter) {
          counter.textContent = `${length} / 10 chars min`;
          if (length >= 10) {
            counter.classList.add('text-success');
            counter.classList.remove('text-muted');
          } else {
            counter.classList.remove('text-success');
            counter.classList.add('text-muted');
          }
        }

        // Enable or disable the reviewer buttons for this proposal
        const form = e.target.closest('.reviewer-action-form');
        if (form) {
          form.querySelectorAll('.reviewer-btn').forEach(btn => {
            btn.disabled = length < 10;
          });
        }
      });
    });

    // Reviewer Queue button click handlers
    document.querySelectorAll('.reviewer-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const action = e.currentTarget.getAttribute('data-action');
        const propId = e.currentTarget.getAttribute('data-id');
        const textarea = document.getElementById(`reviewer-reason-${propId}`);
        const feedback = document.getElementById(`feedback-${propId}`);
        const reason = textarea ? textarea.value.trim() : '';

        if (!reason || reason.length < 10) {
          if (feedback) feedback.innerHTML = '<span class="text-danger font-bold">Error: Written rationale must be at least 10 characters.</span>';
          return;
        }

        btn.disabled = true;
        if (feedback) feedback.innerHTML = '<span class="text-muted">Submitting reviewer attestation...</span>';

        try {
          const res = await api.submitReviewDecision(propId, {
            action,
            reason,
            reviewerAddress: '0xAuditor77777777777777777777777777777777'
          });

          if (res && res.success === false) {
            if (feedback) {
              feedback.innerHTML = `<span class="badge badge-warning">${escapeHTML(res.error)}</span>`;
            }
          } else {
            if (feedback) {
              feedback.innerHTML = `<span class="badge badge-success">Review decision recorded: ${escapeHTML(action)}</span>`;
            }
          }
        } catch (err) {
          if (feedback) {
            feedback.innerHTML = `<span class="badge badge-danger">Submission Failed: ${escapeHTML(err.message)}</span>`;
          }
        } finally {
          btn.disabled = false;
        }
      });
    });

    // Informed Voting: Acknowledgement checkbox & buttons
    const ackCheckbox = document.getElementById('voting-ack-checkbox');
    const voteBtns = document.querySelectorAll('.vote-btn');
    const voteFeedback = document.getElementById('voting-feedback');

    if (ackCheckbox) {
      ackCheckbox.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        voteBtns.forEach(b => {
          b.disabled = !isChecked;
        });
      });
    }

    voteBtns.forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const choice = e.currentTarget.getAttribute('data-choice');
        const selected = store.state.selectedProposal;
        if (!selected) return;

        voteBtns.forEach(b => b.disabled = true);
        if (voteFeedback) {
          voteFeedback.innerHTML = '<span class="text-muted">Submitting vote transaction...</span>';
        }

        try {
          const res = await api.submitVote(selected.id, {
            choice,
            acknowledged: true
          });

          if (res && res.success === false) {
            if (voteFeedback) {
              voteFeedback.innerHTML = `<span class="badge badge-warning">${escapeHTML(res.error)}</span>`;
            }
          } else {
            if (voteFeedback) {
              voteFeedback.innerHTML = `<span class="badge badge-success">Vote successfully recorded for ${escapeHTML(choice)}</span>`;
            }
          }
        } catch (err) {
          if (voteFeedback) {
            voteFeedback.innerHTML = `<span class="badge badge-danger">Vote Failed: ${escapeHTML(err.message)}</span>`;
          }
        } finally {
          if (ackCheckbox && ackCheckbox.checked) {
            voteBtns.forEach(b => b.disabled = false);
          }
        }
      });
    });
  }

  setTab(tab) {
    store.setActiveTab(tab);
  }
}

// Instantiate and attach global instance
window.app = new App();
if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', () => {
    window.app.init();
  });
} else {
  window.app.init();
}
