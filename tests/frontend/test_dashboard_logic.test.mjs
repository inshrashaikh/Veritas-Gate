/**
 * test_dashboard_logic.test.mjs
 * ==============================
 * Native Node.js test suite for Veritas Gate Phase 6 Dashboard JavaScript modules.
 * Run with: node --test tests/frontend/test_dashboard_logic.test.mjs
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { escapeHTML, sanitizeAddress, truncateAddress, formatTokenAmount } from '../../dashboard/js/security.js';
import { CONFIG } from '../../dashboard/js/config.js';
import { DEMO_METRICS, DEMO_PROPOSALS, DEMO_RED_TEAM_ARENA } from '../../dashboard/js/demoData.js';
import { api } from '../../dashboard/js/api.js';
import { StateStore } from '../../dashboard/js/state.js';
import { renderVerdictCard } from '../../dashboard/js/components/verdictCard.js';
import { renderEffectsDiff } from '../../dashboard/js/components/effectsDiff.js';
import { renderEvaluationChain } from '../../dashboard/js/components/evaluationChain.js';
import { renderVotingPanel } from '../../dashboard/js/components/votingPanel.js';
import { renderCoiPanel } from '../../dashboard/js/components/coiPanel.js';

// ---------------------------------------------------------------------------
// 1. Security & XSS Escaping Tests
// ---------------------------------------------------------------------------
test('security: escapeHTML escapes script tags and malicious attributes', () => {
  const dangerous = '<script>alert("XSS")</script>&<img src="x" onerror="steal()"/>\'';
  const clean = escapeHTML(dangerous);
  assert.ok(!clean.includes('<script>'));
  assert.ok(!clean.includes('</script>'));
  assert.ok(!clean.includes('"XSS"'));
  assert.ok(clean.includes('&lt;script&gt;'));
  assert.ok(clean.includes('&amp;'));
  assert.ok(clean.includes('&quot;'));
  assert.ok(clean.includes('&#x27;'));
});

test('security: sanitizeAddress handles valid and malformed addresses', () => {
  const valid = '0x1111111111111111111111111111111111111111';
  assert.equal(sanitizeAddress(valid), valid.toLowerCase());

  const mixed = '0x11111111111111111111111111111111111111Aa';
  assert.equal(sanitizeAddress(mixed), mixed.toLowerCase());

  const invalid = '<script>alert(1)</script>';
  const sanitizedInvalid = sanitizeAddress(invalid);
  assert.ok(!sanitizedInvalid.includes('<script>'));
});

test('security: formatTokenAmount strictly distinguishes missing values from zero', () => {
  const missing = formatTokenAmount(null, 18, 'MOCK');
  assert.equal(missing.isMissing, true);
  assert.equal(missing.formatted, 'Absent / Missing');

  const zero = formatTokenAmount('0', 18, 'MOCK');
  assert.equal(zero.isZero, true);
  assert.equal(zero.isMissing, false);
  assert.equal(zero.formatted, '0 MOCK');

  const fiveM = formatTokenAmount('5000000000000000000000000', 18, 'MOCK');
  assert.equal(fiveM.isMissing, false);
  assert.equal(fiveM.formatted, '5,000,000 MOCK');
  assert.equal(fiveM.exact, '5000000000000000000000000');
});

// ---------------------------------------------------------------------------
// 2. Config & Fail-Closed Defaults Tests
// ---------------------------------------------------------------------------
test('config: demo mode is a boolean and verdict classes exist', () => {
  assert.equal(typeof CONFIG.DEMO_MODE, 'boolean');
  assert.ok(CONFIG.VERDICT_CLASSES.VERIFIED);
  assert.ok(CONFIG.VERDICT_CLASSES.MISMATCH);
  assert.ok(CONFIG.VERDICT_CLASSES.NEEDS_REVIEW);
});

// ---------------------------------------------------------------------------
// 3. Demo Dataset & Phase 1/3 Alignment Tests
// ---------------------------------------------------------------------------
test('demoData: contains all three verdicts and matches Phase 1/3 reason codes', () => {
  assert.ok(DEMO_PROPOSALS.length >= 6);
  
  const statuses = new Set(DEMO_PROPOSALS.map(p => p.verdict?.status));
  assert.ok(statuses.has('VERIFIED'));
  assert.ok(statuses.has('MISMATCH'));
  assert.ok(statuses.has('NEEDS_REVIEW'));

  // Proposal 1: Honest 5M
  const prop1 = DEMO_PROPOSALS.find(p => p.id === 'prop-001');
  assert.equal(prop1.verdict.status, 'VERIFIED');
  assert.equal(prop1.verdict.reasonCode, 'VERIFIED_ALL_CLAIMS_MATCH');

  // Proposal 2: Malicious Slot 0 hijack
  const prop2 = DEMO_PROPOSALS.find(p => p.id === 'prop-002');
  assert.equal(prop2.verdict.status, 'MISMATCH');
  assert.equal(prop2.verdict.reasonCode, 'MISMATCH_OWNERSHIP_COLLISION');
  assert.equal(prop2.observedEffects.ownership.hasMutated, true);

  // Proposal 3: Risky delegatecall
  const prop3 = DEMO_PROPOSALS.find(p => p.id === 'prop-003');
  assert.equal(prop3.verdict.status, 'NEEDS_REVIEW');
  assert.equal(prop3.verdict.reasonCode, 'NEEDS_REVIEW_RISKY_OPERATION_FLAG');

  // Proposal 4: Incomplete trace
  const prop4 = DEMO_PROPOSALS.find(p => p.id === 'prop-004');
  assert.equal(prop4.verdict.traceComplete, false);
  assert.equal(prop4.verdict.reasonCode, 'NEEDS_REVIEW_TRACE_INCOMPLETE');

  // Red Team Arena
  assert.equal(DEMO_RED_TEAM_ARENA.detectionRate, '100% (6/6)');
  assert.equal(DEMO_RED_TEAM_ARENA.missedCount, 0);
});

// ---------------------------------------------------------------------------
// 4. API Client & Action Validation Tests
// ---------------------------------------------------------------------------
test('api: submitReviewDecision requires written reason of minimum 10 characters', async () => {
  await assert.rejects(
    async () => {
      await api.submitReviewDecision('prop-003', { action: 'APPROVE', reason: 'ok' });
    },
    /minimum 10 characters/
  );

  await assert.rejects(
    async () => {
      await api.submitReviewDecision('prop-003', { action: 'INVALID_ACTION', reason: 'valid long rationale here' });
    },
    /Invalid reviewer action/
  );
});

test('api: submitReviewDecision records simulated local decision in demo mode without on-chain execution', async () => {
  CONFIG.DEMO_MODE = true;
  const res = await api.submitReviewDecision('prop-003', {
    action: 'APPROVE',
    reason: 'Verified stateless library call in sandboxed bytecode.'
  });
  assert.equal(res.success, true);
  assert.equal(res.simulated, true);
  assert.equal(res.onChainConfirmed, false);
  assert.equal(res.isDemo, true);
  assert.ok(res.note.includes('NOT an on-chain transaction'));
});

test('api: submitVote requires mandatory comprehension acknowledgement', async () => {
  await assert.rejects(
    async () => {
      await api.submitVote('prop-001', { choice: 'FOR', acknowledged: false });
    },
    /must acknowledge/
  );
});

test('api: submitVote records simulated vote in demo mode without on-chain execution', async () => {
  CONFIG.DEMO_MODE = true;
  const res = await api.submitVote('prop-001', { choice: 'FOR', acknowledged: true });
  assert.equal(res.success, true);
  assert.equal(res.simulated, true);
  assert.equal(res.onChainConfirmed, false);
  assert.equal(res.isDemo, true);
  assert.ok(res.note.includes('NOT submitted to on-chain Governor'));
});

test('state: recordReviewDecision and recordVote update state and reset cleanly', () => {
  const testStore = new StateStore();
  testStore.setProposals(DEMO_PROPOSALS);

  // Record simulated review
  testStore.recordReviewDecision('prop-003', {
    action: 'APPROVE',
    reason: 'Test approved in offline demo',
    simulated: true
  });
  const reviewedProp = testStore.state.proposals.find(p => p.id === 'prop-003');
  assert.equal(reviewedProp.status, 'CLEARED_BY_AUDITOR');
  assert.equal(reviewedProp.reviews.length, 1);

  // Record simulated vote
  testStore.recordVote('prop-001', {
    choice: 'FOR',
    simulated: true
  });
  const votedProp = testStore.state.proposals.find(p => p.id === 'prop-001');
  assert.equal(votedProp.userVote.choice, 'FOR');

  // Reset
  testStore.resetDemoActions();
  testStore.setProposals(DEMO_PROPOSALS);
  const resetProp = testStore.state.proposals.find(p => p.id === 'prop-003');
  assert.equal(resetProp.reviews, undefined);
});

// ---------------------------------------------------------------------------
// 5. State Management & Filtering Tests
// ---------------------------------------------------------------------------
test('state: filtering and sorting work as expected', () => {
  const store = new StateStore();
  store.setProposals(DEMO_PROPOSALS);

  // Filter by VERIFIED
  store.setFilters({ verdict: 'VERIFIED' });
  const verifiedList = store.getFilteredProposals();
  assert.equal(verifiedList.length, 1);
  assert.equal(verifiedList[0].id, 'prop-001');

  // Filter by MISMATCH
  store.setFilters({ verdict: 'MISMATCH' });
  const mismatchList = store.getFilteredProposals();
  assert.equal(mismatchList.length, 2);

  // Search query
  store.setFilters({ verdict: 'ALL', searchQuery: 'hijack' });
  const searchList = store.getFilteredProposals();
  assert.ok(searchList.some(p => p.id === 'prop-002'));
});

// ---------------------------------------------------------------------------
// 6. UI Components Rendering Tests
// ---------------------------------------------------------------------------
test('components: renderVerdictCard outputs matching verdict and reason', () => {
  const prop1 = DEMO_PROPOSALS[0];
  const html1 = renderVerdictCard(prop1);
  assert.ok(html1.includes('VERIFIED'));
  assert.ok(html1.includes('VERIFIED_ALL_CLAIMS_MATCH'));
  assert.ok(html1.includes('verdict-header-verified'));

  const prop2 = DEMO_PROPOSALS[1];
  const html2 = renderVerdictCard(prop2);
  assert.ok(html2.includes('MISMATCH'));
  assert.ok(html2.includes('MISMATCH_OWNERSHIP_COLLISION'));
  assert.ok(html2.includes('verdict-header-mismatch'));
});

test('components: renderEffectsDiff renders exact match and unclaimed drains', () => {
  const prop1 = DEMO_PROPOSALS[0];
  const html1 = renderEffectsDiff(prop1);
  assert.ok(html1.includes('EXACT MATCH'));
  assert.ok(html1.includes('5,000,000 MOCK'));

  const prop5 = DEMO_PROPOSALS.find(p => p.id === 'prop-005');
  const html5 = renderEffectsDiff(prop5);
  assert.ok(html5.includes('UNCLAIMED TRANSFER'));
  assert.ok(html5.includes('DRAIN DETECTED'));
});

test('components: renderEvaluationChain declares all 4 stages with limitations', () => {
  const prop1 = DEMO_PROPOSALS[0];
  const html = renderEvaluationChain(prop1);
  assert.ok(html.includes('Claim Confidence'));
  assert.ok(html.includes('COI Risk'));
  assert.ok(html.includes('Voting Readiness'));
  assert.ok(html.includes('Execution Discrepancy'));
  assert.ok(html.includes('Methodological Limitations'));
  assert.ok(html.includes('strictly refuses to fabricate numerical Bayesian percentages'));
});

test('components: renderVotingPanel renders disabled vote buttons until checked', () => {
  const prop1 = DEMO_PROPOSALS[0];
  const html = renderVotingPanel(prop1, true);
  assert.ok(html.includes('voting-ack-checkbox'));
  assert.ok(html.includes('disabled'));
  assert.ok(html.includes('acknowledgement of having viewed'));
});

test('components: renderCoiPanel renders mandatory disclaimer', () => {
  const prop2 = DEMO_PROPOSALS[1];
  const html = renderCoiPanel(prop2);
  assert.ok(html.includes('Conflict of Interest'));
  assert.ok(html.includes('Never claim common ownership solely from a transfer'));
});
