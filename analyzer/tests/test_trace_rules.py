"""Unit tests for security trace rules and incomplete trace handling."""

from analyzer.trace_rules import (
    APPROVAL_EVENT_TOPIC,
    EIP1967_IMPLEMENTATION_SLOT,
    UPGRADED_EVENT_TOPIC,
    TraceAnalyzer,
)


def test_detect_delegatecall_call_tracer():
    call_tracer_data = {
        "type": "CALL",
        "from": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "to": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",
        "calls": [
            {
                "type": "DELEGATECALL",
                "from": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",
                "to": "0xcafac3dd18ac6c6e92c92183187b327334960395",
                "gas": "0x1234",
                "input": "0x97ec0d08",
            }
        ],
    }
    analyzer = TraceAnalyzer(raw_trace=call_tracer_data, is_complete=True)
    is_ok, findings, errors = analyzer.analyze(logs=[], state_diffs=[])

    assert is_ok is True
    assert len(errors) == 0
    rule_ids = [f.rule_id for f in findings]
    assert "R001_DELEGATECALL" in rule_ids
    delegate_finding = next(f for f in findings if f.rule_id == "R001_DELEGATECALL")
    assert delegate_finding.severity == "HIGH"
    assert delegate_finding.evidence["target"] is None or delegate_finding.evidence.get("to") == "0xcafac3dd18ac6c6e92c92183187b327334960395"


def test_detect_delegatecall_parity_trace():
    parity_trace = [
        {
            "action": {
                "callType": "delegatecall",
                "from": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",
                "to": "0xcafac3dd18ac6c6e92c92183187b327334960395",
                "value": "0x0",
            },
            "type": "call",
        }
    ]
    analyzer = TraceAnalyzer(raw_trace=parity_trace, is_complete=True)
    is_ok, findings, errors = analyzer.analyze(logs=[], state_diffs=[])

    assert is_ok is True
    rule_ids = [f.rule_id for f in findings]
    assert "R001_DELEGATECALL" in rule_ids


def test_detect_selfdestruct_structlogs():
    struct_logs = {
        "structLogs": [
            {"pc": 100, "op": "PUSH1"},
            {"pc": 102, "op": "SELFDESTRUCT", "gas": 5000},
        ]
    }
    analyzer = TraceAnalyzer(raw_trace=struct_logs, is_complete=True)
    is_ok, findings, errors = analyzer.analyze(logs=[], state_diffs=[])

    assert is_ok is True
    rule_ids = [f.rule_id for f in findings]
    assert "R002_SELFDESTRUCT" in rule_ids
    sd_finding = next(f for f in findings if f.rule_id == "R002_SELFDESTRUCT")
    assert sd_finding.severity == "HIGH"


def test_detect_proxy_upgrade_log_and_slot():
    logs = [
        {
            "address": "0x1111111111111111111111111111111111111111",
            "topics": [
                UPGRADED_EVENT_TOPIC,
                "0x0000000000000000000000002222222222222222222222222222222222222222",
            ],
            "data": "0x",
        }
    ]
    state_diffs = [
        {
            "effect_id": f"storage_slot:0x1111111111111111111111111111111111111111:{EIP1967_IMPLEMENTATION_SLOT}",
            "effect_type": "storage_slot",
            "address": "0x1111111111111111111111111111111111111111",
            "before_value": "0x0000000000000000000000001111111111111111111111111111111111111111",
            "after_value": "0x0000000000000000000000002222222222222222222222222222222222222222",
        }
    ]
    analyzer = TraceAnalyzer(raw_trace={}, is_complete=True)
    is_ok, findings, errors = analyzer.analyze(logs=logs, state_diffs=state_diffs)

    rule_ids = [f.rule_id for f in findings]
    assert "R003_PROXY_UPGRADE" in rule_ids
    # Both the log and the slot write triggered R003
    proxy_findings = [f for f in findings if f.rule_id == "R003_PROXY_UPGRADE"]
    assert len(proxy_findings) == 2


def test_detect_unlimited_approval():
    max_uint256 = (1 << 256) - 1
    max_uint256_hex = hex(max_uint256)

    logs = [
        {
            "address": "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0",
            "topics": [
                APPROVAL_EVENT_TOPIC,
                "0x000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb92266",
                "0x00000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c8",
            ],
            "data": max_uint256_hex,
        }
    ]
    analyzer = TraceAnalyzer(raw_trace={}, is_complete=True)
    is_ok, findings, errors = analyzer.analyze(logs=logs, state_diffs=[])

    rule_ids = [f.rule_id for f in findings]
    assert "R004_UNLIMITED_APPROVAL" in rule_ids
    finding = next(f for f in findings if f.rule_id == "R004_UNLIMITED_APPROVAL")
    assert finding.severity == "MEDIUM"


def test_incomplete_trace_handling():
    analyzer = TraceAnalyzer(raw_trace=None, is_complete=False, trace_error="RPC endpoint does not support tracing")
    is_ok, findings, errors = analyzer.analyze(logs=[], state_diffs=[])

    assert is_ok is False
    assert len(errors) == 1
    assert "Incomplete trace: RPC endpoint does not support tracing" in errors[0]
    rule_ids = [f.rule_id for f in findings]
    assert "R000_INCONCLUSIVE_TRACE" in rule_ids
    inconclusive = next(f for f in findings if f.rule_id == "R000_INCONCLUSIVE_TRACE")
    assert inconclusive.severity == "WARNING"
