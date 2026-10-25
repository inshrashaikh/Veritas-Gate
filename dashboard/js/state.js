/**
 * state.js
 * ========
 * Reactive state store for Veritas Gate Phase 6 Dashboard.
 * Includes local persistence and reset capabilities for demo interactions.
 */

import { STORAGE_KEYS } from './config.js';

export class StateStore {
  constructor() {
    this.state = {
      proposals: [],
      selectedProposal: null,
      metrics: null,
      redTeamData: null,
      challenges: [],
      guardianEvents: [],
      
      filters: {
        searchQuery: '',
        verdict: 'ALL',
        status: 'ALL',
        sortBy: 'date_desc'
      },
      
      activeTab: 'overview', // 'overview' | 'explorer' | 'detail' | 'reviewer' | 'challenges' | 'redteam'
      loading: false,
      error: null,
      isDemoData: false
    };

    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error('State listener error:', err);
      }
    }
  }

  setLoading(loading) {
    this.state.loading = Boolean(loading);
    this.notify();
  }

  setError(error) {
    this.state.error = error ? String(error) : null;
    this.notify();
  }

  setDemoData(isDemo) {
    this.state.isDemoData = Boolean(isDemo);
    this.notify();
  }

  setMetrics(metrics) {
    this.state.metrics = metrics;
    this.notify();
  }

  setProposals(proposals) {
    this.state.proposals = Array.isArray(proposals) ? proposals.map(p => ({ ...p })) : [];
    // If in demo mode, apply persisted local demo interactions
    if (this.state.isDemoData) {
      this.loadPersistedDemoActions();
    }
    // If no proposal selected or previously selected proposal exists, re-sync selection
    if (this.state.selectedProposal) {
      const reFound = this.state.proposals.find(p => p.id === this.state.selectedProposal.id);
      this.state.selectedProposal = reFound || (this.state.proposals.length > 0 ? this.state.proposals[0] : null);
    } else if (this.state.proposals.length > 0) {
      this.state.selectedProposal = this.state.proposals[0];
    }
    this.notify();
  }

  setSelectedProposal(proposal) {
    this.state.selectedProposal = proposal;
    this.notify();
  }

  selectProposalById(id) {
    const found = this.state.proposals.find(p => p.id === id);
    if (found) {
      this.setSelectedProposal(found);
    }
  }

  recordReviewDecision(proposalId, reviewData) {
    const prop = this.state.proposals.find(p => p.id === proposalId);
    if (prop) {
      if (!prop.reviews) prop.reviews = [];
      prop.reviews.push(reviewData);

      // Update proposal status according to reviewer action
      if (reviewData.action === 'APPROVE') {
        prop.status = 'CLEARED_BY_AUDITOR';
        if (prop.verdict) {
          prop.verdict.reviewedStatus = 'APPROVED_BY_AUDITOR';
        }
      } else if (reviewData.action === 'REJECT') {
        prop.status = 'REJECTED_BY_AUDITOR';
        if (prop.verdict) {
          prop.verdict.reviewedStatus = 'REJECTED_BY_AUDITOR';
        }
      } else if (reviewData.action === 'ESCALATE') {
        prop.status = 'ESCALATED_TO_MULTISIG';
        if (prop.verdict) {
          prop.verdict.reviewedStatus = 'ESCALATED';
        }
      }

      this.persistDemoActions();
      this.notify();
    }
  }

  recordVote(proposalId, voteData) {
    const prop = this.state.proposals.find(p => p.id === proposalId);
    if (prop) {
      prop.userVote = voteData;
      this.persistDemoActions();
      this.notify();
    }
  }

  persistDemoActions() {
    try {
      if (typeof localStorage !== 'undefined') {
        const reviews = {};
        const votes = {};
        for (const p of this.state.proposals) {
          if (p.reviews && p.reviews.length > 0) reviews[p.id] = p.reviews;
          if (p.userVote) votes[p.id] = p.userVote;
          if (p.status) reviews[`${p.id}_status`] = p.status;
        }
        localStorage.setItem(STORAGE_KEYS.DEMO_REVIEWS, JSON.stringify(reviews));
        localStorage.setItem(STORAGE_KEYS.DEMO_VOTES, JSON.stringify(votes));
      }
    } catch (_) {}
  }

  loadPersistedDemoActions() {
    try {
      if (typeof localStorage !== 'undefined') {
        const reviewsRaw = localStorage.getItem(STORAGE_KEYS.DEMO_REVIEWS);
        const votesRaw = localStorage.getItem(STORAGE_KEYS.DEMO_VOTES);
        if (reviewsRaw) {
          const reviews = JSON.parse(reviewsRaw);
          for (const p of this.state.proposals) {
            if (reviews[p.id]) p.reviews = reviews[p.id];
            if (reviews[`${p.id}_status`]) p.status = reviews[`${p.id}_status`];
          }
        }
        if (votesRaw) {
          const votes = JSON.parse(votesRaw);
          for (const p of this.state.proposals) {
            if (votes[p.id]) p.userVote = votes[p.id];
          }
        }
      }
    } catch (_) {}
  }

  resetDemoActions() {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem(STORAGE_KEYS.DEMO_REVIEWS);
        localStorage.removeItem(STORAGE_KEYS.DEMO_VOTES);
      }
    } catch (_) {}
  }

  setFilters(partialFilters) {
    this.state.filters = {
      ...this.state.filters,
      ...partialFilters
    };
    this.notify();
  }

  setActiveTab(tab) {
    this.state.activeTab = tab;
    this.notify();
  }

  setRedTeamData(data) {
    this.state.redTeamData = data;
    this.notify();
  }

  setChallenges(challenges) {
    this.state.challenges = Array.isArray(challenges) ? challenges : [];
    this.notify();
  }

  setGuardianEvents(events) {
    this.state.guardianEvents = Array.isArray(events) ? events : [];
    this.notify();
  }

  /**
   * Filter and sort proposals according to active filters.
   */
  getFilteredProposals() {
    let list = [...this.state.proposals];
    const { searchQuery, verdict, status, sortBy } = this.state.filters;

    // Search query
    if (searchQuery && searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(p => {
        const idMatch = (p.id || '').toLowerCase().includes(q);
        const titleMatch = (p.title || '').toLowerCase().includes(q);
        const proposerMatch = (p.proposer || '').toLowerCase().includes(q);
        const descMatch = (p.description || '').toLowerCase().includes(q);
        return idMatch || titleMatch || proposerMatch || descMatch;
      });
    }

    // Verdict filter
    if (verdict && verdict !== 'ALL') {
      list = list.filter(p => (p.verdict?.status || '').toUpperCase() === verdict.toUpperCase());
    }

    // Status filter
    if (status && status !== 'ALL') {
      list = list.filter(p => (p.status || '').toUpperCase() === status.toUpperCase());
    }

    // Sorting
    list.sort((a, b) => {
      if (sortBy === 'date_asc') {
        return new Date(a.submittedAt || 0) - new Date(b.submittedAt || 0);
      }
      if (sortBy === 'date_desc') {
        return new Date(b.submittedAt || 0) - new Date(a.submittedAt || 0);
      }
      if (sortBy === 'verdict') {
        const rank = { MISMATCH: 1, NEEDS_REVIEW: 2, VERIFIED: 3 };
        const rankA = rank[a.verdict?.status] || 9;
        const rankB = rank[b.verdict?.status] || 9;
        return rankA - rankB;
      }
      return 0;
    });

    return list;
  }
}

export const store = new StateStore();
