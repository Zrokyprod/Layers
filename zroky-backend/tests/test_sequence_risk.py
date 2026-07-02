from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.sequence_risk import (
    SEQUENCE_BLOCK,
    SEQUENCE_HOLD,
    _Step,
    detect_sequence_pattern,
)


_T0 = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def _step(
    action_id: str,
    *,
    at: datetime = _T0,
    kind: str = "read",
    action_type: str = "",
    external: bool = False,
    read: bool = False,
    money: bool = False,
    credential: bool = False,
    trace_id: str | None = "trace-1",
) -> _Step:
    return _Step(
        action_id=action_id,
        operation_kind=kind,
        action_type=action_type,
        created_at=at,
        trace_id=trace_id,
        is_external=external,
        is_read_or_export=read,
        is_money=money,
        is_credential_update=credential,
    )


def test_no_signal_for_isolated_action():
    current = _step("a1", external=True)
    assert detect_sequence_pattern(current, prior=[]) is None


def test_read_then_external_send_holds():
    prior = [_step("a1", kind="read", read=True)]
    current = _step("a2", kind="send", external=True, action_type="send_email")
    signal = detect_sequence_pattern(current, prior)
    assert signal is not None
    assert signal.recommended == SEQUENCE_HOLD
    assert signal.pattern == "sensitive_read_then_external_send"
    assert "a1" in signal.contributing_action_ids and "a2" in signal.contributing_action_ids


def test_external_send_without_prior_read_is_ignored():
    # A lone external send is the single-action policy's job, not a sequence.
    prior = [_step("a1", kind="update", action_type="update_ticket")]
    current = _step("a2", kind="send", external=True)
    assert detect_sequence_pattern(current, prior) is None


def test_credential_change_then_external_export_blocks():
    prior = [_step("a1", kind="update", action_type="reset_password", credential=True)]
    current = _step("a2", kind="send", external=True, read=True, action_type="export_users")
    signal = detect_sequence_pattern(current, prior)
    assert signal is not None
    assert signal.recommended == SEQUENCE_BLOCK
    assert signal.confidence == "high"
    assert signal.pattern == "credential_change_then_external_transfer"


def test_credential_change_then_email_send_holds_not_blocks():
    # Ambiguous outward channel (plain email, no url/export) => HOLD, not BLOCK.
    prior = [_step("a1", kind="update", action_type="reset_password", credential=True)]
    current = _step("a2", kind="send", external=True, action_type="send_email")
    signal = detect_sequence_pattern(current, prior)
    assert signal is not None
    assert signal.recommended == SEQUENCE_HOLD
    assert signal.confidence == "medium"


def test_three_money_actions_in_window_holds():
    prior = [
        _step("a1", kind="transfer", money=True, at=_T0 - timedelta(minutes=5)),
        _step("a2", kind="transfer", money=True, at=_T0 - timedelta(minutes=2)),
    ]
    current = _step("a3", kind="transfer", money=True, at=_T0)
    signal = detect_sequence_pattern(current, prior)
    assert signal is not None
    assert signal.recommended == SEQUENCE_HOLD
    assert signal.pattern == "rapid_repeated_money_movement"


def test_two_money_actions_below_threshold():
    prior = [_step("a1", kind="transfer", money=True, at=_T0 - timedelta(minutes=2))]
    current = _step("a2", kind="transfer", money=True, at=_T0)
    assert detect_sequence_pattern(current, prior) is None


def test_money_actions_outside_window_do_not_count():
    prior = [
        _step("a1", kind="transfer", money=True, at=_T0 - timedelta(minutes=40)),
        _step("a2", kind="transfer", money=True, at=_T0 - timedelta(minutes=30)),
    ]
    current = _step("a3", kind="transfer", money=True, at=_T0)
    assert detect_sequence_pattern(current, prior) is None
