/**
 * api.js
 * ======
 * API Client module for Veritas Gate Phase 6 Dashboard.
 * 
 * Rules:
 * - Real API client using CONFIG.API_BASE_URL.
 * - Clear error handling with loading states and transparent status reporting.
 * - NEVER silently replaces failed API responses with fake success data.
 * - If DEMO_MODE is enabled, routes to demoData with explicit [DEMO DATA] tags.
 * - In DEMO_MODE, actions (reviews, votes) simulate functional local workflows while explicitly declaring onChainConfirmed: false.
 * - In Live mode, mutations call the real backend and reject without confirmation.
 */

import { CONFIG } from './config.js';
import {
  DEMO_METRICS,
  DEMO_PROPOSALS,
  DEMO_RED_TEAM_ARENA,
  DEMO_CHALLENGES,
  DEMO_GUARDIAN_EVENTS
} from './demoData.js';

class ApiClient {
  constructor() {
    this.isLiveAvailable = null;
    this.lastError = null;
  }

  async _fetch(endpoint, options = {}) {
    const url = `${CONFIG.API_BASE_URL.replace(/\/$/, '')}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          ...(options.headers || {})
        }
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorMsg = `HTTP Error ${response.status} (${response.statusText})`;
        try {
          const errData = await response.json();
          if (errData && (errData.detail || errData.error || errData.message)) {
            errorMsg = errData.detail || errData.error || errData.message;
          }
        } catch (_) {}
        throw new Error(errorMsg);
      }

      const data = await response.json();
      this.isLiveAvailable = true;
      this.lastError = null;
      return { data, isDemo: false };
    } catch (err) {
      clearTimeout(timeoutId);
      this.isLiveAvailable = false;
      const baseErr = err.name === 'AbortError' ? 'Request timed out' : (err.message || 'Network connection failed');
      this.lastError = `${baseErr} (Target: ${CONFIG.API_BASE_URL})`;
      throw new Error(this.lastError);
    }
  }

  async fetchMetrics() {
    if (CONFIG.DEMO_MODE) {
      return { data: DEMO_METRICS, isDemo: true };
    }
    return await this._fetch('/metrics');
  }

  async fetchProposals() {
    if (CONFIG.DEMO_MODE) {
      return { data: DEMO_PROPOSALS, isDemo: true };
    }
    return await this._fetch('/proposals');
  }

  async fetchProposalById(proposalId) {
    if (CONFIG.DEMO_MODE) {
      const found = DEMO_PROPOSALS.find(p => p.id === proposalId);
      if (!found) {
        throw new Error(`Proposal '${proposalId}' not found in demo dataset.`);
      }
      return { data: found, isDemo: true };
    }
    return await this._fetch(`/proposals/${encodeURIComponent(proposalId)}`);
  }

  async fetchRedTeamArena() {
    if (CONFIG.DEMO_MODE) {
      return { data: DEMO_RED_TEAM_ARENA, isDemo: true };
    }
    return await this._fetch('/red-team');
  }

  async fetchChallenges() {
    if (CONFIG.DEMO_MODE) {
      return { data: DEMO_CHALLENGES, isDemo: true };
    }
    return await this._fetch('/challenges');
  }

  async fetchGuardianEvents() {
    if (CONFIG.DEMO_MODE) {
      return { data: DEMO_GUARDIAN_EVENTS, isDemo: true };
    }
    return await this._fetch('/guardian');
  }

  /**
   * Submit Reviewer Decision.
   * STRICT: Requires non-empty reason (minimum 10 chars).
   * Demo mode records a simulated local decision without submitting blockchain transactions.
   */
  async submitReviewDecision(proposalId, { action, reason, reviewerAddress }) {
    if (!action || !['APPROVE', 'REJECT', 'ESCALATE'].includes(action)) {
      throw new Error(`Invalid reviewer action: '${action}'. Must be APPROVE, REJECT, or ESCALATE.`);
    }
    if (!reason || typeof reason !== 'string' || reason.trim().length < 10) {
      throw new Error('Mandatory written reason required (minimum 10 characters).');
    }

    if (CONFIG.DEMO_MODE) {
      // Functional demo simulation with safe separation: local record only, never an on-chain transaction
      return {
        success: true,
        simulated: true,
        action,
        reason: reason.trim(),
        reviewer: reviewerAddress || '0xAuditor77777777777777777777777777777777',
        isDemo: true,
        onChainConfirmed: false,
        timestamp: new Date().toISOString(),
        note: 'Simulated local demonstration record — NOT an on-chain transaction or real signature.'
      };
    }

    // Call real API
    return await this._fetch(`/proposals/${encodeURIComponent(proposalId)}/reviews`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        reason: reason.trim(),
        reviewer: reviewerAddress || 'anonymous_reviewer',
        timestamp: new Date().toISOString()
      })
    });
  }

  /**
   * Submit Informed Vote.
   * STRICT: Requires acknowledgement checkbox.
   * Demo mode records a simulated local ballot without submitting to on-chain Governor.
   */
  async submitVote(proposalId, { choice, acknowledged }) {
    if (!acknowledged) {
      throw new Error('You must acknowledge that you have seen the real effects before voting.');
    }
    if (!choice || !['FOR', 'AGAINST', 'ABSTAIN'].includes(choice)) {
      throw new Error(`Invalid vote choice: '${choice}'. Must be FOR, AGAINST, or ABSTAIN.`);
    }

    if (CONFIG.DEMO_MODE) {
      // Functional demo simulation with safe separation: local ballot acknowledgement only
      return {
        success: true,
        simulated: true,
        choice,
        acknowledged: true,
        isDemo: true,
        onChainConfirmed: false,
        timestamp: new Date().toISOString(),
        note: 'Simulated local ballot acknowledgement — NOT submitted to on-chain Governor.'
      };
    }

    // Call real API
    return await this._fetch(`/proposals/${encodeURIComponent(proposalId)}/vote`, {
      method: 'POST',
      body: JSON.stringify({
        choice,
        acknowledged: true,
        timestamp: new Date().toISOString()
      })
    });
  }
}

export const api = new ApiClient();
