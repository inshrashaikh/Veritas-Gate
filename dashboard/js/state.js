/**
 * state.js
 * ========
 * Reactive state store for Veritas Gate Phase 6 Dashboard.
 */

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
    this.state.proposals = Array.isArray(proposals) ? proposals : [];
    // If no proposal selected, select the first one if available
    if (!this.state.selectedProposal && this.state.proposals.length > 0) {
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
        // Order: MISMATCH first (critical), then NEEDS_REVIEW, then VERIFIED
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
