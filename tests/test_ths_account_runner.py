# AI-SUMMARY: 同花顺多账户编排测试——全 mock 覆盖串行、弹窗跳过、10 户上限、异常退出和落盘可见性
from contextlib import nullcontext

import pytest

from execution.ths_account_runner import run_ths_account_workflow
from execution.ths_account_ui import FundAccountRef


def _cfg(ths_count=2, fund_limit=10):
    return {
        "execution": {
            "mode": "dry_run",
            "ths_account_switch": {
                "hexin_path": "C:/ths/hexin.exe",
                "xiadan_path": "C:/ths/xiadan.exe",
                "max_ths_accounts": ths_count,
                "max_fund_accounts_per_ths": fund_limit,
                "accounts": [
                    {"username": "mx_one", "enabled": True},
                    {"username": "mx_two", "enabled": True},
                ],
            },
        },
        "gui": {
            "ths_account_switch": {"restart_timeout_s": 1, "login_wait_s": 1},
            "xiadan": {"fund_account_control_id": 1711, "account_combo_control_id": 2322},
            "lifecycle": {"close_after_task": True, "close_timeout_s": 1},
        },
        "strategy": {"blacklist": []},
    }


def _refs(count, prefix="a"):
    base = 1000000000 + sum(ord(char) for char in prefix) * 1000
    return [
        FundAccountRef.from_label(i, f"券商-{prefix}{i:02d}-{base + i}")
        for i in range(count)
    ]


class FakeUI:
    def __init__(self, refs, login_status="ready", xiadan_error=None, dialogs=None):
        self.refs = refs
        self.login_status = login_status
        self.xiadan_error = xiadan_error
        self.dialogs = dialogs or {}
        self.events = []

    def ensure_xiadan_ready(self):
        self.events.append("xiadan")
        if self.xiadan_error:
            raise self.xiadan_error

    def discover_fund_accounts(self):
        self.events.append("discover")
        return list(self.refs)

    def login_fund_account(self, ref):
        self.events.append(("login", ref.index))
        self.ensure_xiadan_ready()
        status = self.dialogs.get(ref.index, self.login_status)
        return {
            "target_key": ref.key,
            "display_text": ref.display_masked,
            "fund_account_hash": ref.fund_account_hash,
            "fund_account_masked": ref.fund_account_masked,
            "fund_account_tail4": ref.fund_account_tail4,
            "status": status,
            "dialog_required": status == "dialog_required",
            "manual_required": False,
            "xiadan_present": status in {"ready", "already_logged_in", "wrong_account"},
            "error_code": "" if status in {"ready", "already_logged_in"} else status.upper(),
            "error": "",
        }

    def close_main_window(self):
        self.events.append("close_main")

    def wait_for_popup(self, timeout_s, action="切换账号"):
        self.events.append(("wait_popup", action))
        return True

    def click_popup(self, action):
        self.events.append(("popup", action))
        return True

    def wait_for_client_exit(self, timeout_s):
        self.events.append("wait_exit")
        return True

    def save_screenshot(self, name):
        return f"runtime_data/screenshots/{name}"


class FakeLifecycle:
    def __init__(self, events, start_error=None):
        self.events = events
        self.start_error = start_error

    def start(self):
        self.events.append("start")
        if self.start_error:
            raise self.start_error

    def close(self):
        self.events.append("close")
        return {"status": "closed"}


def _run(cfg, ui, events, *, task_status="completed", writer=None, lifecycle=None):
    call_count = {"n": 0}

    def factory(_client, _cfg):
        call_count["n"] += 1
        return ui if call_count["n"] == 1 else FakeUI(_refs(1, "b"))

    def switch(target, _client, _reader, _ui, _timeout):
        events.append(("switch", target.username))
        return {"username": target.username, "status": "switched"}

    def task(ctx):
        events.append(("task", ctx.ths_username, ctx.fund_account["target_key"]))
        return {"status": task_status}

    lifecycle = lifecycle or FakeLifecycle(events)
    return run_ths_account_workflow(
        cfg,
        day="2026-10-17",
        live=False,
        ui_factory=factory,
        lifecycle_factory=lambda _client, _cfg: lifecycle,
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=switch,
        password_reader=lambda _username: "secret",
        account_task=task,
        result_writer=writer or (lambda _snapshot: None),
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )


def test_direct_login_runs_task_and_writes_result():
    events = []
    ui = FakeUI(_refs(1))
    result = _run(_cfg(ths_count=1), ui, events)
    assert result["status"] == "completed"
    assert result["ths_accounts"][0]["fund_accounts"][0]["status"] == "completed"
    assert events[0] == "start"
    assert events[-1] == "close"
    assert ("task", "mx_one", ui.refs[0].key) in events


def test_password_dialog_is_closed_and_next_fund_continues():
    events = []
    ui = FakeUI(_refs(2), dialogs={0: "dialog_required"})
    result = _run(_cfg(ths_count=1), ui, events)
    rows = result["ths_accounts"][0]["fund_accounts"]
    assert [row["status"] for row in rows] == ["dialog_required", "completed"]
    assert rows[0]["dialog_required"] is True
    assert rows[0]["manual_required"] is False
    assert [event for event in events if isinstance(event, tuple) and event[0] == "task"] == [
        ("task", "mx_one", ui.refs[1].key)
    ]


def test_fund_account_limit_stops_after_ten_ready_accounts():
    events = []
    ui = FakeUI(_refs(11))
    result = _run(_cfg(ths_count=1, fund_limit=10), ui, events)
    assert len(result["ths_accounts"][0]["fund_accounts"]) == 10
    assert result["ths_accounts"][0]["fund_limit_reached"] is True
    assert len([e for e in events if isinstance(e, tuple) and e[0] == "task"]) == 10


def test_fund_account_limit_skips_login_dialogs_but_stops_at_ten_rows():
    events = []
    ui = FakeUI(_refs(12), dialogs={0: "dialog_required", 1: "dialog_required"})
    result = _run(_cfg(ths_count=1, fund_limit=10), ui, events)
    rows = result["ths_accounts"][0]["fund_accounts"]
    assert [row["login_status"] for row in rows[:2]] == ["dialog_required", "dialog_required"]
    assert sum(row["login_status"] == "ready" for row in rows) == 8
    assert len(rows) == 10
    assert result["ths_accounts"][0]["fund_limit_reached"] is True


def test_wrong_account_never_runs_task():
    events = []
    ui = FakeUI(_refs(1), login_status="wrong_account")
    result = _run(_cfg(ths_count=1), ui, events)
    assert result["ths_accounts"][0]["fund_accounts"][0]["status"] == "wrong_account"
    assert not any(isinstance(e, tuple) and e[0] == "task" for e in events)


def test_duplicate_fund_account_is_skipped_globally():
    events = []
    shared = _refs(1, "same")[0]
    ui = FakeUI([shared])
    cfg = _cfg()
    cfg["execution"]["ths_account_switch"]["accounts"].append({"username": "mx_three", "enabled": True})
    result = run_ths_account_workflow(
        cfg,
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: ui,
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle(events),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username,
            "status": "switched",
        },
        password_reader=lambda _username: "secret",
        account_task=lambda _ctx: {"status": "completed"},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )
    statuses = [
        row["status"]
        for ths in result["ths_accounts"]
        for row in ths["fund_accounts"]
    ]
    assert statuses == ["completed", "duplicate_account"]


def test_missing_xiadan_records_error_and_continues_to_next_ths():
    events = []
    cfg = _cfg()
    call_count = {"n": 0}

    def factory(_client, _cfg):
        call_count["n"] += 1
        return FakeUI(
            _refs(1, chr(ord("a") + call_count["n"])),
            xiadan_error=RuntimeError("xiadan missing"),
        )

    result = run_ths_account_workflow(
        cfg,
        day="2026-10-17",
        ui_factory=factory,
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle(events),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username,
            "status": "switched",
        },
        password_reader=lambda _username: "secret",
        account_task=lambda _ctx: {"status": "completed"},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )
    assert [row["status"] for row in result["ths_accounts"]] == [
        "xiadan_failed",
        "xiadan_failed",
    ]


def test_startup_failure_still_closes_gently():
    events = []
    lifecycle = FakeLifecycle(events, start_error=RuntimeError("start failed"))
    result = _run(_cfg(ths_count=1), FakeUI(_refs(1)), events, lifecycle=lifecycle)
    assert result["status"] == "failed"
    assert result["error_code"] == "THS_WORKFLOW_START_FAILED"
    assert events == ["start", "close"]


def test_two_ths_accounts_are_strictly_serial():
    events = []
    result = _run(_cfg(), FakeUI(_refs(1)), events)
    assert result["status"] == "completed"
    assert [item for item in events if isinstance(item, tuple) and item[0] == "switch"] == [
        ("switch", "mx_one"),
        ("switch", "mx_two"),
    ]
    tasks = [item for item in events if isinstance(item, tuple) and item[0] == "task"]
    assert [item[1] for item in tasks] == ["mx_one", "mx_two"]


def test_result_writer_failure_is_visible_but_does_not_hide_results():
    def writer(_snapshot):
        raise OSError("disk full")

    result = _run(_cfg(ths_count=1), FakeUI(_refs(1)), [], writer=writer)
    assert result["status"] == "completed"
    assert result["result_write_errors"]
    assert "disk full" not in str(result)
    assert result["ths_accounts"][0]["fund_accounts"][0]["status"] == "completed"


def test_default_task_passes_full_filtered_allowlist_to_batch(monkeypatch):
    from execution import allotment, ipo_page, login, order_ledger, subscribe, ths_client
    from execution.ths_account_runner import ThsAccountTaskContext, default_account_task

    calendar = {
        "cbs": [{"code": "110000", "name": "转债", "apply_code": "110000"}],
        "new_stocks": [
            {"name": "新股", "apply_code": "600000", "issue_price": 10, "apply_limit": 1000},
            {"name": "黑名单", "apply_code": "600001", "issue_price": 10, "apply_limit": 1000},
        ],
    }
    calls = {}
    real_calendar_allowlist = subscribe.calendar_allowlist

    monkeypatch.setattr("data_fetch.calendar.fetch_calendar_for", lambda _day: calendar)
    monkeypatch.setattr(
        "execution.subscribe.calendar_allowlist",
        lambda cal, blacklist=None: real_calendar_allowlist(cal, blacklist),
    )

    def batch(_user, **kwargs):
        calls["allowlist"] = kwargs["allowlist"]
        calls["blacklist"] = kwargs["blacklist"]
        return [{"apply_code": "600000", "status": "submitted"}]

    monkeypatch.setattr("execution.ipo_page.batch_subscribe", batch)
    monkeypatch.setattr("execution.subscribe.execute", lambda _user, orders, _mode, **_kwargs: [
        {**order, "status": "dry_run"} for order in orders
    ])
    monkeypatch.setattr("execution.ths_client.connect", lambda client=None: object())
    monkeypatch.setattr("execution.ths_client.read_today_entrusts_via_ocr", lambda _user: [])
    monkeypatch.setattr("execution.allotment.query_allotment", lambda _user: [])
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda client=None: 0)
    monkeypatch.setattr("execution.order_ledger.OrderLedger", lambda _day, **_kwargs: object())

    ctx = ThsAccountTaskContext(
        day="2026-10-17",
        live=True,
        mode="live",
        ths_username="mx_one",
        fund_account={"target_key": "hash", "fund_account_hash": "hash"},
        client=object(),
        cfg={"strategy": {"blacklist": ["600001"]}},
    )
    result = default_account_task(ctx)
    assert result["status"] == "completed"
    assert [row["apply_code"] for row in calls["allowlist"]] == ["110000", "600000"]
    assert calls["blacklist"] == ["600001"]


# --- phase routing and P0 safety tests ---

def _phase_spy_task(calls, result=None):
    def task(ctx):
        calls.append(ctx)
        return dict(result or {"status": "completed"})
    return task


def test_switch_result_dataclass_is_accepted():
    from execution.ths_account_switch import ThsAccountSwitchResult

    events = []
    result = run_ths_account_workflow(
        _cfg(ths_count=1),
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle(events),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: ThsAccountSwitchResult(
            username=target.username,
            status="switched",
        ),
        password_reader=lambda _username: "secret",
        account_task=lambda _ctx: {"status": "completed"},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )
    assert result["ths_accounts"][0]["switch_status"] == "switched"


def test_login_phase_skips_task_and_only_sends_login_receipt():
    calls = []
    receipts = []
    result = run_ths_account_workflow(
        _cfg(ths_count=1),
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle([]),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username, "status": "switched",
        },
        password_reader=lambda _username: "secret",
        phase="login",
        account_task=_phase_spy_task(calls, {
            "status": "completed",
            "subscribe": [{"apply_code": "110000", "status": "submitted"}],
            "allotment": [{"apply_code": "110000", "status": "won"}],
        }),
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda kind, payload: receipts.append((kind, payload)) or {"sent": True},
    )
    row = result["ths_accounts"][0]["fund_accounts"][0]
    assert calls == []
    assert row["login_status"] == "ready"
    assert row["task_status"] == "not_run"
    assert row["status"] == "completed"
    assert "subscribe" not in row
    assert "allotment" not in row
    assert [kind for kind, _ in receipts] == ["login"]
    assert receipts[0][1]["items"][0]["login_status"] == "ready"


def test_allotment_phase_never_subscribes_and_keeps_query_items(monkeypatch):
    from execution import ipo_page, subscribe as subscribe_mod, ths_client
    from execution.ths_account_runner import ThsAccountTaskContext, default_account_task

    query_calls = []
    # 2026-10-24 起中签过滤需要当日申购代码（防历史中签误当当日结果），允许读日历
    monkeypatch.setattr("data_fetch.calendar.fetch_calendar_for", lambda _day: {
        "day": _day, "new_stocks": [], "cbs": [{"name": "华纬转债", "code": "110000", "apply_code": "110000"}],
    })
    monkeypatch.setattr("execution.ths_client.connect", lambda client=None: object())
    monkeypatch.setattr("execution.ipo_page.batch_subscribe", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("allotment-only 不得申购")))
    monkeypatch.setattr("execution.subscribe.execute", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("allotment-only 不得申购")))
    monkeypatch.setattr("execution.allotment.query_allotment", lambda _user: query_calls.append(1) or [{
        "证券名称": "华纬转债", "证券代码": "110000", "中签数量": 10, "缴款金额": 1000,
    }])
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda client=None: 0)

    result = default_account_task(ThsAccountTaskContext(
        day="2026-10-17",
        live=False,
        mode="dry_run",
        phase="allotment",
        ths_username="mx_one",
        fund_account={"target_key": "hash", "fund_account_hash": "hash"},
        client=object(),
        cfg={},
    ))
    assert query_calls == [1]
    assert result["status"] == "completed"
    assert result["allotment"][0]["证券代码"] == "110000"
    assert "subscribe" not in result


def test_subscribe_phase_skips_allotment_query(monkeypatch):
    from execution.ths_account_runner import ThsAccountTaskContext, default_account_task

    events = []
    monkeypatch.setattr("data_fetch.calendar.fetch_calendar_for", lambda _day: {
        "cbs": [{"code": "110000", "name": "转债", "apply_code": "110000"}],
        "new_stocks": [],
    })
    monkeypatch.setattr("execution.ths_client.connect", lambda client=None: object())
    monkeypatch.setattr("execution.subscribe.calendar_allowlist", lambda _cal, blacklist=None: [
        {"code": "110000", "apply_code": "110000", "name": "转债", "price": 100, "amount": 1000, "unit": "张"},
    ])
    monkeypatch.setattr("execution.ipo_page.batch_subscribe", lambda *_a, **_k: events.append("subscribe") or [
        {"apply_code": "110000", "status": "dry_run"},
    ])
    monkeypatch.setattr("execution.allotment.query_allotment", lambda _user: events.append("allotment") or [])
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda client=None: 0)

    result = default_account_task(ThsAccountTaskContext(
        day="2026-10-17",
        live=False,
        mode="dry_run",
        phase="subscribe",
        ths_username="mx_one",
        fund_account={"target_key": "hash"},
        client=object(),
        cfg={},
    ))
    assert events == ["subscribe"]
    assert result["subscribe"][0]["status"] == "dry_run"
    assert "allotment" not in result


@pytest.mark.parametrize("row_status, expected", [
    ("unknown", "partial"),
    ("submitted_unverified", "partial"),
    ("failed", "failed"),
    ("failed_confirmed", "failed"),
    ("batch_rejected", "failed"),
])
def test_default_task_aggregate_status_never_completed_for_bad_rows(monkeypatch, row_status, expected):
    from execution.ths_account_runner import ThsAccountTaskContext, default_account_task

    monkeypatch.setattr("data_fetch.calendar.fetch_calendar_for", lambda _day: {
        "cbs": [{"code": "110000", "name": "转债", "apply_code": "110000"}],
        "new_stocks": [],
    })
    monkeypatch.setattr("execution.ths_client.connect", lambda client=None: object())
    monkeypatch.setattr("execution.subscribe.calendar_allowlist", lambda _cal, blacklist=None: [
        {"code": "110000", "apply_code": "110000", "name": "转债", "price": 100, "amount": 1000, "unit": "张"},
    ])
    monkeypatch.setattr("execution.ipo_page.batch_subscribe", lambda *_a, **_k: [
        {"apply_code": "110000", "status": row_status},
    ])
    monkeypatch.setattr("execution.allotment.query_allotment", lambda _user: [])
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda client=None: 0)

    result = default_account_task(ThsAccountTaskContext(
        day="2026-10-17",
        live=False,
        mode="dry_run",
        phase="subscribe",
        ths_username="mx_one",
        fund_account={"target_key": "hash"},
        client=object(),
        cfg={},
    ))
    assert result["status"] == expected


def test_receipts_use_phase_specific_items_and_no_allotment_receipt_without_query():
    receipts = []
    result = run_ths_account_workflow(
        _cfg(ths_count=1),
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle([]),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username, "status": "switched",
        },
        password_reader=lambda _username: "secret",
        phase="all",
        account_task=lambda _ctx: {
            "status": "completed",
            "subscribe": [{"apply_code": "110000", "status": "submitted"}],
            "allotment": [{"证券代码": "110000", "中签数量": 1}],
        },
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda kind, payload: receipts.append((kind, payload)) or {"sent": True},
    )
    assert [kind for kind, _ in receipts] == ["login", "subscribe", "allotment"]
    assert receipts[0][1]["items"][0]["login_status"] == "ready"
    assert receipts[1][1]["items"][0]["apply_code"] == "110000"
    assert receipts[1][1]["items"][0]["status"] == "submitted"
    assert receipts[2][1]["items"][0]["winning_qty"] == 1
    assert result["ths_accounts"][0]["subscribe"][0]["apply_code"] == "110000"
    assert result["ths_accounts"][0]["allotment"][0]["证券代码"] == "110000"
    from scheduler.catchup import _ths_phase_items
    assert _ths_phase_items(result["ths_accounts"], "subscribe")[0]["apply_code"] == "110000"
    assert _ths_phase_items(result["ths_accounts"], "allotment")[0]["apply_code"] == "110000"

    receipts.clear()
    run_ths_account_workflow(
        _cfg(ths_count=1),
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle([]),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username, "status": "switched",
        },
        password_reader=lambda _username: "secret",
        phase="subscribe",
        account_task=lambda _ctx: {"status": "completed", "subscribe": [], "allotment": []},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda kind, payload: receipts.append((kind, payload)) or {"sent": True},
    )
    assert [kind for kind, _ in receipts] == ["subscribe"]


def test_startup_failure_does_not_send_business_receipt():
    receipts = []
    result = run_ths_account_workflow(
        _cfg(ths_count=1),
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle([], start_error=RuntimeError("start failed")),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username, "status": "switched",
        },
        password_reader=lambda _username: "secret",
        account_task=lambda _ctx: {"status": "completed"},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda kind, payload: receipts.append((kind, payload)) or {"sent": True},
    )
    assert result["status"] == "failed"
    assert receipts == []


def test_default_result_writer_uses_atomic_replace(tmp_path, monkeypatch):
    import json
    from execution.ths_account_runner import default_result_writer

    monkeypatch.setattr("shared.paths.ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr("shared.paths.runtime_path", lambda *parts: tmp_path / parts[-1])
    writer = default_result_writer("2026-10-17")
    writer({"status": "running"})
    writer({"status": "completed"})
    path = tmp_path / "2026-10-17.json"
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "completed"
    assert list(tmp_path.glob("*.tmp")) == []


def test_default_lock_factory_uses_shared_gui_lock(monkeypatch):
    used = []
    monkeypatch.setattr(
        "execution.ths_account_runner.gui_lock",
        lambda operation: used.append(operation) or nullcontext(),
    )
    run_ths_account_workflow(
        _cfg(ths_count=1),
        day="2026-10-17",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle([]),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username, "status": "switched",
        },
        password_reader=lambda _username: "secret",
        account_task=lambda _ctx: {"status": "completed"},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )
    assert used == ["ths_account_switch"]


@pytest.mark.parametrize("blocked", ["110000", "711000"])
def test_default_task_blacklist_matches_code_or_apply_code(monkeypatch, blocked):
    from execution.ths_account_runner import ThsAccountTaskContext, default_account_task

    captured = {}
    order = {"code": "110000", "apply_code": "711000", "name": "转债", "price": 100,
             "amount": 1000, "unit": "张"}
    monkeypatch.setattr("data_fetch.calendar.fetch_calendar_for", lambda _day: {"cbs": [], "new_stocks": []})
    monkeypatch.setattr("execution.subscribe.calendar_allowlist", lambda _cal, blacklist=None: [order])
    monkeypatch.setattr("execution.ths_client.connect", lambda client=None: object())
    monkeypatch.setattr("execution.ipo_page.batch_subscribe", lambda _user, **kwargs: captured.update(kwargs) or [])
    monkeypatch.setattr("execution.subscribe.uncovered_orders", lambda _orders, _rows: [])
    monkeypatch.setattr("execution.subscribe.execute", lambda *_a, **_k: [])
    monkeypatch.setattr("execution.allotment.query_allotment", lambda _user: [])
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda client=None: 0)
    monkeypatch.setattr("execution.order_ledger.OrderLedger", lambda _day, **_kwargs: object())

    default_account_task(ThsAccountTaskContext(
        day="2026-10-17",
        live=True,
        mode="live",
        phase="subscribe",
        ths_username="mx_one",
        fund_account={"target_key": "hash"},
        client=object(),
        cfg={"strategy": {"blacklist": [blocked]}},
    ))
    assert captured["allowlist"] == []
    assert captured["blacklist"] == [blocked]


def test_expired_subscribe_is_not_executed(monkeypatch):
    events = []
    monkeypatch.setattr("execution.subscribe.live_run_allowed", lambda _day: False)
    monkeypatch.setattr("data_fetch.calendar.fetch_calendar_for", lambda _day: events.append("calendar") or {})
    monkeypatch.setattr("execution.ths_client.connect", lambda client=None: events.append("connect") or object())
    monkeypatch.setattr("execution.ipo_page.batch_subscribe", lambda *_a, **_k: events.append("batch") or [])
    monkeypatch.setattr("execution.subscribe.execute", lambda *_a, **_k: events.append("execute") or [])
    monkeypatch.setattr("execution.allotment.query_allotment", lambda _user: events.append("allotment") or [])

    cfg = _cfg(ths_count=1)
    cfg["execution"]["mode"] = "live"
    result = run_ths_account_workflow(
        cfg,
        day="2026-10-17",
        live=True,
        phase="subscribe",
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle([]),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username, "status": "switched",
        },
        password_reader=lambda _username: "secret",
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )
    row = result["ths_accounts"][0]["fund_accounts"][0]
    assert events == []
    assert result["mode"] == "skipped_expired"
    assert row["login_status"] == "ready"
    assert row["task_status"] == "skipped_expired"
    assert row["status"] == "completed"
    assert row["subscribe"] == [{"status": "skipped", "reason": "申购时段已过，不执行申购"}]
# RED: 每个 THS 最多记录/处理 max_fund_accounts_per_ths 户。
def test_each_ths_never_processes_more_than_configured_limit():
    events = []
    ui = FakeUI(_refs(13), dialogs={index: "dialog_required" for index in range(13)})
    result = _run(_cfg(ths_count=1, fund_limit=10), ui, events)
    rows = result["ths_accounts"][0]["fund_accounts"]
    assert len(rows) == 10
    assert result["ths_accounts"][0]["fund_limit_reached"] is True
    assert len([e for e in ui.events if isinstance(e, tuple) and e[0] == "login"]) == 10
    assert not [e for e in events if isinstance(e, tuple) and e[0] == "task"]

def test_each_ths_account_gets_independent_client_lifecycle():
    events = []
    result = run_ths_account_workflow(
        _cfg(ths_count=2, fund_limit=1),
        day="2026-10-17",
        live=False,
        ui_factory=lambda _client, _cfg: FakeUI(_refs(1)),
        lifecycle_factory=lambda _client, _cfg: FakeLifecycle(events),
        lock_factory=lambda _operation: nullcontext(),
        account_switcher=lambda target, _client, _reader, _ui, _timeout: {
            "username": target.username,
            "status": "switched",
        },
        password_reader=lambda _username: "secret",
        account_task=lambda _ctx: {"status": "completed"},
        result_writer=lambda _snapshot: None,
        receipt_sender=lambda _kind, _payload: {"sent": False},
    )

    assert events == ["start", "close", "start", "close"]
    assert result["lifecycle_closes"] == [{"status": "closed"}, {"status": "closed"}]



# RED: phase items 不丢资金账户显示文本，并携带可去重身份字段。
def test_phase_items_keeps_fund_identity_and_account_key():
    from execution.ths_account_runner import _phase_items

    result = {"ths_accounts": [{
        "username": "mx_test",
        "fund_accounts": [{
            "target_key": "fund-1",
            "display_text": "平安证券-张*龙",
            "fund_account": "326219242115",
            "fund_account_tail4": "2115",
            "login_status": "ready",
            "status": "completed",
        }],
    }]}
    items = _phase_items(result, "login")
    assert items[0]["display_name"] == "平安证券-张*龙"
    assert items[0]["account_key"] == "fund-1"
    assert items[0]["ths_account"] == "mx_test"
    assert items[0]["fund_account"] == "326219242115"
def test_allotment_filter_drops_history_without_matching_code():
    """中签过滤：历史日期行丢弃；日期缺失且代码不属于当日申购标的的行丢弃。"""
    from execution.ths_account_runner import _allotment_row_belongs

    codes = {"070887"}
    assert _allotment_row_belongs({"中签日期": "2026-10-23", "apply_code": "070887"}, "2026-10-22", codes)
    assert not _allotment_row_belongs({"中签日期": "2026-10-23", "apply_code": "110000"}, "2026-10-22", codes)
    assert not _allotment_row_belongs({"中签日期": "2026-06-01", "apply_code": "070887"}, "2026-10-22", codes)
    assert not _allotment_row_belongs({"apply_code": "110000"}, "2026-10-22", codes)  # 无日期+非当日标的
    assert _allotment_row_belongs({"证券代码": "070887"}, "2026-10-22", codes)       # 无日期但当日标的
