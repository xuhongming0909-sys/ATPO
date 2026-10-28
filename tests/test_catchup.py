# AI-SUMMARY: catch-up 与 ths-cycle 幂等编排单测——交易日门、状态机、回执补发、生命周期验收
from datetime import datetime

import pytest

from scheduler import catchup
from shared.task_state import TaskStateStore


@pytest.fixture()
def store(tmp_path):
    return TaskStateStore(path=tmp_path / "task_state.json")


@pytest.fixture(autouse=True)
def _all_trading_days(monkeypatch):
    monkeypatch.setattr(catchup, "is_trading_day", lambda day: True)


CFG = {
    "catchup": {"enabled": True, "subscribe_skip_after": "15:00", "allotment_retry_interval_min": 30,
                "allotment_keep_days": 3},
    "schedule": {"subscribe_window": ["09:30", "15:00"], "allotment_check_1": "22:00"},
    "notification_receipts": {"template_version": 2, "send_login": True, "send_subscribe": True,
                              "send_allotment": True},
}


def _workflow_result(status="completed", username="mx_1"):
    return {
        "day": "2026-10-21",
        "status": status,
        "ths_accounts": [{
            "username": username,
            "status": status,
            "fund_accounts": [{
                "display_name": "许*鸣",
                "fund_account": "88012345",
                "login_status": "ready",
                "status": status,
                "subscribe": [{"name": "华纬转债", "apply_code": "071123", "amount": 10000,
                               "unit": "张", "status": "submitted", "reason": ""}],
            }],
        }],
        "close_errors": [],
        "lifecycle_close": {"status": "closed"},
    }


def test_catch_up_skips_non_trading_day(monkeypatch, store):
    monkeypatch.setattr(catchup, "is_trading_day", lambda day: False)
    out = catchup.catch_up("2026-10-25", live=True, cfg=CFG, store=store)
    assert out["status"] == "skipped_non_trading"
    assert store.list() == []


def test_catch_up_disabled_short_circuits(store):
    out = catchup.catch_up("2026-10-21", cfg={"catchup": {"enabled": False}}, store=store)
    assert out["catchup"]["status"] == "disabled"


def test_catch_up_daily_report_completed_not_repeated(store):
    store.record("daily_report", "2026-10-21", "completed", receipt_status="sent", mode="live")
    called = []
    out = catchup.catch_up("2026-10-21", live=False, cfg=CFG, store=store,
                           daily_report=lambda **kw: called.append(kw) or [],
                           send_receipt=lambda kind, data: "sent")
    assert out["daily_report"]["status"] == "skipped_completed"
    assert called == []


def test_ths_cycle_subscribe_expired_marked_not_replayed(store, tmp_path):
    now = datetime(2026, 10, 21, 16, 0)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: "sent",
                                workflow=lambda **kw: pytest.fail("不应启动 GUI"))
    assert out["subscribe"]["status"] == "skipped_expired"
    state = store.get("subscribe", "2026-10-21", "live")
    assert state.status == "skipped_expired"


def test_ths_cycle_pending_window_before_subscribe_open(store):
    now = datetime(2026, 10, 21, 9, 0)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: "sent",
                                workflow=lambda **kw: pytest.fail("不应启动 GUI"))
    assert out["subscribe"]["status"] == "pending_window"


def test_ths_cycle_skips_non_trading_business_day(monkeypatch, store):
    monkeypatch.setattr(catchup, "is_trading_day", lambda day: False)
    now = datetime(2026, 10, 21, 10, 0)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: "sent",
                                workflow=lambda **kw: pytest.fail("不应启动 GUI"))
    assert out["subscribe"]["status"] == "skipped_non_trading"


def test_ths_cycle_runs_workflow_and_sends_receipt(store):
    now = datetime(2026, 10, 21, 10, 30)
    sent = []
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: sent.append((kind, data)) or "sent",
                                workflow=lambda **kw: _workflow_result(),
                                process_probe=lambda: {"status": "clean", "residual_processes": []})
    assert out["subscribe"]["status"] == "completed"
    assert sent and sent[0][0] == "subscribe"
    assert store.get("subscribe", "2026-10-21", "live").status == "completed"


def test_ths_cycle_same_result_dedups_receipt(store):
    now = datetime(2026, 10, 21, 10, 30)
    receipt_calls = []
    kwargs = dict(live=True, cfg=CFG, store=store, now=now,
                  receipt=lambda kind, data: receipt_calls.append(kind) or "sent",
                  workflow=lambda **kw: _workflow_result(),
                  process_probe=lambda: {"status": "clean", "residual_processes": []})
    catchup.run_ths_cycle("2026-10-21", "subscribe", **kwargs)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", **kwargs)
    assert out["subscribe"]["status"] == "skipped_completed"
    assert receipt_calls == ["subscribe"]  # 申购回执不重复推送


def test_ths_cycle_blocked_uncertain_never_replays(store):
    store.record("subscribe", "2026-10-21", "blocked_uncertain", receipt_status="sent",
                 mode="live", payload={"receipt_data": {"date": "2026-10-21"}})
    now = datetime(2026, 10, 21, 10, 30)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: "sent",
                                workflow=lambda **kw: pytest.fail("不确定状态禁止重放"))
    assert out["subscribe"]["status"] == "blocked_uncertain"


def test_ths_cycle_retries_missing_receipt_from_state(store):
    payload = {"receipt_data": {"date": "2026-10-21", "summary": {}, "items": []},
               "items": [], "result_signature": "sig"}
    store.record("subscribe", "2026-10-21", "completed", receipt_status="failed",
                 mode="live", payload=payload)
    sent = []
    now = datetime(2026, 10, 21, 10, 30)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: sent.append(kind) or "sent",
                                workflow=lambda **kw: pytest.fail("回执补发不启动 GUI"))
    assert out["subscribe"]["status"] == "receipt_retried"
    assert sent == ["subscribe"]


def test_ths_cycle_lifecycle_probe_residual_flagged(store):
    now = datetime(2026, 10, 21, 10, 30)
    out = catchup.run_ths_cycle("2026-10-21", "subscribe", live=True, cfg=CFG, store=store,
                                now=now, receipt=lambda kind, data: "sent",
                                workflow=lambda **kw: _workflow_result(),
                                process_probe=lambda: {"status": "residual",
                                                       "residual_processes": [{"image_name": "hexin.exe", "count": 1}]})
    assert out["lifecycle"]["status"] == "lifecycle_failed"


def test_allotment_business_day_falls_back_to_latest_subscribe(store):
    store.record("subscribe", "2026-10-19", "completed", receipt_status="sent", mode="live")
    from datetime import date
    assert catchup.allotment_business_day(store, date(2026, 10, 21)) == "2026-10-19"


def test_failed_gui_without_items_is_not_completed(store):
    now = datetime(2026, 10, 21, 10, 0)
    out = catchup.run_ths_cycle(
        "2026-10-21", "subscribe", live=True, cfg=CFG, store=store, now=now,
        receipt=lambda kind, data: "sent",
        workflow=lambda **kw: {"status": "failed", "ths_accounts": []},
        process_probe=lambda: {"status": "clean", "residual_processes": []},
    )
    assert out["subscribe"]["status"] == "retryable"
