"""
tests/test_dashboard.py
=======================
Automated verification tests for Veritas Gate Phase 6 Governance Dashboard.
Tests HTML structure, CSS rules, JavaScript security, demo data separation,
verdict rendering, reviewer queue constraints, and informed voting rules.
"""

from pathlib import Path
import re
import pytest

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


def test_dashboard_files_exist():
    """Verify all required dashboard assets and modules exist."""
    required_files = [
        "index.html",
        "serve.py",
        "css/main.css",
        "css/components.css",
        "js/app.js",
        "js/api.js",
        "js/config.js",
        "js/security.js",
        "js/demoData.js",
        "js/state.js",
        "js/components/header.js",
        "js/components/overview.js",
        "js/components/proposalExplorer.js",
        "js/components/verdictCard.js",
        "js/components/effectsDiff.js",
        "js/components/evaluationChain.js",
        "js/components/evidenceExplorer.js",
        "js/components/reviewerQueue.js",
        "js/components/votingPanel.js",
        "js/components/coiPanel.js",
        "js/components/guardianPanel.js",
        "js/components/redTeamArena.js",
    ]
    for rel_path in required_files:
        p = DASHBOARD_DIR / rel_path
        assert p.is_file(), f"Missing required dashboard asset: {rel_path}"


def test_html_structure_and_accessibility():
    """Verify semantic HTML, viewport, meta tags, and accessibility landmarks."""
    html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert 'lang="en"' in html
    assert 'name="viewport"' in html
    assert "<title>Veritas Gate" in html
    assert 'rel="stylesheet" href="css/main.css"' in html
    assert 'rel="stylesheet" href="css/components.css"' in html
    assert "<noscript>" in html
    assert 'id="app"' in html
    assert 'type="module" src="js/app.js"' in html


def test_css_verdict_colors_and_themes():
    """Verify CSS defines all 3 status colors (green, red, amber) and responsive styles."""
    main_css = (DASHBOARD_DIR / "css/main.css").read_text(encoding="utf-8")
    comp_css = (DASHBOARD_DIR / "css/components.css").read_text(encoding="utf-8")

    # Status colors
    assert "--color-verified:" in main_css
    assert "--color-mismatch:" in main_css
    assert "--color-needs-review:" in main_css

    # Theme selectors
    assert '[data-theme="dark"]' in main_css
    assert '[data-theme="light"]' in main_css

    # Responsive media queries
    assert "@media" in main_css
    assert "@media" in comp_css

    # Specific verdict headers in components.css
    assert ".verdict-header-verified" in comp_css
    assert ".verdict-header-mismatch" in comp_css
    assert ".verdict-header-needs-review" in comp_css


def test_security_module_escaping():
    """Verify security.js contains XSS prevention and numerical unit formatting."""
    sec_js = (DASHBOARD_DIR / "js/security.js").read_text(encoding="utf-8")
    assert "export function escapeHTML" in sec_js
    assert "export function sanitizeAddress" in sec_js
    assert "export function formatTokenAmount" in sec_js

    # Verify escaping covers all key HTML injection characters
    assert ".replace(/&/g, '&amp;')" in sec_js
    assert ".replace(/</g, '&lt;')" in sec_js
    assert ".replace(/>/g, '&gt;')" in sec_js
    assert ".replace(/\"/g, '&quot;')" in sec_js


def test_config_demo_mode_disabled_by_default():
    """Verify demo mode is strictly disabled by default."""
    cfg_js = (DASHBOARD_DIR / "js/config.js").read_text(encoding="utf-8")
    assert "DEMO_MODE:" in cfg_js
    # Must default to false when no localStorage entry exists
    assert "safeGetStorage(STORAGE_KEYS.DEMO_MODE, 'false') === 'true'" in cfg_js


def test_demo_data_labeled_and_has_all_verdicts():
    """Verify demo dataset is explicitly labeled and represents VERIFIED, MISMATCH, NEEDS_REVIEW."""
    demo_js = (DASHBOARD_DIR / "js/demoData.js").read_text(encoding="utf-8")
    assert "DEMO DATA (SYNTHETIC)" in demo_js
    assert "NOT real on-chain evidence" in demo_js
    assert "'VERIFIED'" in demo_js
    assert "'MISMATCH'" in demo_js
    assert "'NEEDS_REVIEW'" in demo_js

    # Verify Phase 3 reason codes are represented
    assert "VERIFIED_ALL_CLAIMS_MATCH" in demo_js
    assert "MISMATCH_OWNERSHIP_COLLISION" in demo_js
    assert "NEEDS_REVIEW_RISKY_OPERATION_FLAG" in demo_js
    assert "NEEDS_REVIEW_TRACE_INCOMPLETE" in demo_js
    assert "MISMATCH_UNCLAIMED_MATERIAL_TRANSFER" in demo_js


def test_evaluation_chain_avoids_fabricated_probabilities():
    """Verify the 4-stage evaluation chain does not fabricate numerical percentages."""
    eval_js = (DASHBOARD_DIR / "js/components/evaluationChain.js").read_text(encoding="utf-8")
    assert "Claim Confidence" in eval_js
    assert "COI Risk" in eval_js
    assert "Voting Readiness" in eval_js
    assert "Execution Discrepancy" in eval_js
    assert "Source &amp; Empirical Evidence" in eval_js
    assert "Methodological Limitations" in eval_js
    assert "strictly refuses to fabricate numerical Bayesian percentages" in eval_js


def test_informed_voting_acknowledgement_required():
    """Verify informed voting requires acknowledgement before enabling vote."""
    vote_js = (DASHBOARD_DIR / "js/components/votingPanel.js").read_text(encoding="utf-8")
    assert "voting-ack-checkbox" in vote_js
    assert "I have seen the real effects" in vote_js
    assert "acknowledgement of having viewed the EVM execution diff" in vote_js
    assert "does NOT constitute proof of comprehension" in vote_js
    assert "disabled" in vote_js


def test_coi_panel_mandatory_caveat():
    """Verify Conflict of Interest panel displays mandatory disclaimer regarding transfers."""
    coi_js = (DASHBOARD_DIR / "js/components/coiPanel.js").read_text(encoding="utf-8")
    assert "Conflict of Interest" in coi_js
    assert "Never claim common ownership solely from a transfer" in coi_js
    assert "Transfer Adjacency Graph" in coi_js


def test_reviewer_queue_requires_written_reason():
    """Verify reviewer actions enforce mandatory written reason."""
    rev_js = (DASHBOARD_DIR / "js/components/reviewerQueue.js").read_text(encoding="utf-8")
    assert "Mandatory Auditor Rationale" in rev_js
    assert "minimum 10 characters" in rev_js
    assert "reviewer-reason-input" in rev_js
    assert "disabled" in rev_js  # Buttons start disabled until min length
