# AI-SUMMARY: 流程加固测试——死锁检测、申购窗口门、F8 重连、网格重读、北交所路由
import os
from datetime import datetime

import pytest

from scheduler import catchup as cu
from shared.errors import AutoIpoError
from shared.paths import runtime_path
from shared.task_state import TaskStateStore


CFG = {
    "catchup": {"enabled": True, "subscribe_skip_after": "15:00"},
    "schedule": {"subscribe_window": ["09:30", "15:00"]},
    "execution": {"mode": "live", "ths_account_switch": {
        "hexin_path": "C:/ths/hexin.exe", "xiadan_path": "C:/ths/xiadan.exe",
        "max_ths_accounts": 1, "max_fund_accounts_per_ths": 10,
        "accounts": [{"username": "mx_one", "enabled": True}]}},
    "gui": {"ths_account_switch": {"restart_timeout_s": 1, "login_wait_s": 1}},
    "strategy": {"blacklist": []},
}


def _dead_pid() -> int:
    pid = 399999997
    while cu.os.path.exists(f"/proc/{pid}"):  # pragma: no cover - windows 无 /proc
        pid -= 1
    return pid


def test_chain_lock_breaks_when_owner_process_dead():
    from shared.gui_lock import _pid_active

    pid = 399999997
    assert not _pid_active(pid), "测试前提：PID 必须不存在"
    lock = runtime_path("catchup.lock")
    assert not lock.exists(), "测试前提：当前无真实锁"
    try:
        lock.write_text(f"{pid}|ths-cycle|2026-10-20T13:59:22|deadbeef", encoding="utf-8")
        with cu._task_chain_lock("test", timeout_s=0.5):
            pass
    finally:
        lock.unlink(missing_ok=True)


def test_subscribe_before_window_never_marks_completed(tmp_path):
    store = TaskStateStore(tmp_path / "state.json")
    calls = []

    def workflow(**kw):
        calls.append(kw)
        return {"mode": "skipped_expired", "status": "completed", "ths_accounts": []}

    out = cu.run_ths_cycle("2026-10-20", "subscribe", live=True, cfg=CFG, store=store,
                           workflow=workflow, now=datetime(2026, 10, 20, 7, 48),
                           receipt=lambda *a: "sent", process_probe=lambda: {"status": "clean"})
    assert calls == [], "申购窗口未开始不得启动 GUI 申购流程"
    state = store.get("subscribe", "2026-10-20", "live")
    assert state is None or state.status != "completed", "窗口前空跑不得记 completed"

    out2 = cu.run_ths_cycle("2026-10-20", "subscribe", live=True, cfg=CFG, store=store,
                            workflow=workflow, now=datetime(2026, 10, 20, 10, 0),
                            receipt=lambda *a: "sent", process_probe=lambda: {"status": "clean"})
    assert calls, "窗口内必须真正执行申购流程"


import execution.subscribe as sub


class _StaleThenOkUser:
    def __init__(self):
        self.entrust_calls = 0

    def buy(self, code, price, amount):
        return {"message": "success"}

    @property
    def today_entrusts(self):
        self.entrust_calls += 1
        raise RuntimeError("Handle 3606840 is not a vaild window handle")


class _OkUser:
    @property
    def today_entrusts(self):
        return [{"证券代码": "371018", "委托数量": "10000", "委托状态": "已报"}]


def test_execute_reconnects_xiadan_and_rechecks_entrusts(monkeypatch):
    import execution.ths_client as tc

    stale_user = _StaleThenOkUser()
    calls = {"query": 0}

    def query(user):
        calls["query"] += 1
        if user is stale_user:
            raise RuntimeError("Handle 3606840 is not a vaild window handle")
        return [{"\u8bc1\u5238\u4ee3\u7801": "371018", "\u59d4\u6258\u6570\u91cf": "10000", "\u59d4\u6258\u72b6\u6001": "\u5df2\u62a5"}]

    monkeypatch.setattr(tc, "read_today_entrusts_via_ocr", query)
    monkeypatch.setattr(tc, "connect", lambda **kw: _OkUser())
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda **kw: None)
    order = {"name": "申菱转债", "apply_code": "371018", "price": 100.0, "amount": 10000}
    results = sub.execute(stale_user, [order], "live", client_id="mx_one", client=object())
    assert calls["query"] == 2
    assert results[0]["status"] == "submitted", "F8 句柄失效应重连 xiadan 后复查"


import execution.ipo_page as ipo


class _GridUser:
    _main = None
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = 0

    def _switch_left_menus(self, path):
        pass

    def _get_grid_data(self, cid):
        self.calls += 1
        return self.pages.pop(0)


def test_read_ipo_grid_retries_until_codes_present(monkeypatch):
    import execution.ths_client as tc

    monkeypatch.setattr(ipo.time, "sleep", lambda _s: None)
    good = [{"申购代码": "371018", "新股名称": "申菱转债", "申购上限": "10000"}]
    pages = [[{"申购代码": ""}], good]
    monkeypatch.setattr(tc, "read_grid_via_ocr", lambda *a, **k: pages.pop(0))
    rows = ipo.read_ipo_grid(_GridUser([]))
    assert rows == good


def test_read_ipo_grid_gives_up_after_bounded_retries(monkeypatch):
    import execution.ths_client as tc

    monkeypatch.setattr(ipo.time, "sleep", lambda _s: None)
    monkeypatch.setattr(tc, "read_grid_via_ocr", lambda *a, **k: [{"申购代码": ""}])
    rows = ipo.read_ipo_grid(_GridUser([]))
    assert rows == [{"申购代码": ""}]


class _NoBuyUser:
    def buy(self, *a):
        raise AssertionError("北交所代码禁止走买入表单")


def test_bse_code_never_uses_single_buy_form(monkeypatch):
    monkeypatch.setattr("execution.login.close_modal_dialogs", lambda **kw: None)
    order = {"name": "天元重工", "apply_code": "920306", "price": 4.48, "amount": 1819000}
    results = sub.execute(_NoBuyUser(), [order], "live", client_id="mx_one", client=object())
    assert results[0]["status"] == "skipped"
    assert "北交所" in results[0]["reason"]

# AI-SUMMARY: 菜单缓存复用 + login 阶段窗口前门测试
from datetime import datetime

import execution.ths_account_ui as tui
from scheduler import catchup as cu
from shared.task_state import TaskStateStore
from tests.test_flow_hardening import CFG


class _MenuFakeUI:
    """最小化 ThsAccountUI 替身：验证 _click_main_row 复用 discover 缓存的菜单行。"""

    pass


def test_click_main_row_reuses_cached_menu_rows():
    from execution.ths_account_model import FundAccountRef

    calls = {"open": 0, "read": 0, "click": 0}

    ui = tui.ThsAccountUI.__new__(tui.ThsAccountUI)
    ui._menu_rows = [
        {"index": 0, "text": "平安证券-张*龙", "click_x": 100, "click_y": 30, "source": "ocr"},
    ]
    ui._open_menu_fn = lambda: calls.__setitem__("open", calls["open"] + 1) or "menu"
    def _read(_menu):
        calls["read"] += 1
        raise AssertionError("有缓存菜单行时不得重新 OCR 读取")
    ui._read_rows_fn = _read
    ui._close_menu_fn = lambda: None
    def _click(_menu, row, total):
        calls["click"] += 1
        assert row["text"] == "平安证券-张*龙"
    ui._click_row_fn = _click

    ref = FundAccountRef.from_label(0, "平安证券-张*龙")
    row = ui._click_main_row(ref)
    assert calls == {"open": 1, "read": 0, "click": 1}
    assert row["text"] == "平安证券-张*龙"


def test_login_phase_skipped_before_subscribe_window(tmp_path):
    store = TaskStateStore(tmp_path / "state.json")
    calls = []

    def workflow(**kw):
        calls.append(kw)
        return {"mode": "live", "status": "completed", "ths_accounts": []}

    out = cu.run_ths_cycle("2026-10-20", "all", live=True, cfg=CFG, store=store,
                           workflow=workflow, now=datetime(2026, 10, 20, 7, 48),
                           receipt=lambda *a: "sent", process_probe=lambda: {"status": "clean"})
    phases_run = [kw.get("phase") for kw in calls]
    assert "login" not in phases_run and "subscribe" not in phases_run, "申购窗口前 login/subscribe 均不得启动 GUI"
    assert out["login"]["status"] == "pending_window"
    assert out["subscribe"]["status"] == "pending_window"

# AI-SUMMARY: read_menu_rows 双参数签名回归（调用方传 settings）
def test_read_menu_rows_accepts_settings_arg():
    import execution.hexin_login as hl

    rows = hl.read_menu_rows(0, {})
    assert rows == []

# AI-SUMMARY: 中签幻影防护——无效网格行不算中签，无证据不得默认 won
import pytest

from scheduler.catchup import _ths_phase_items


def test_allotment_row_without_identity_is_not_a_win():
    rows = [{"username": "mx_test",
             "allotment": [{"全部完成。汇总：": "## 交付清单"}]}]
    items = _ths_phase_items(rows, "allotment")
    assert items == [] or all(i.get("status") != "won" for i in items)


def test_allotment_valid_row_is_a_win():
    rows = [{"username": "mx_test",
             "allotment": [{"证券名称": "申菱转债", "证券代码": "127258", "中签数量": "10",
                            "account": "平安证券-张*龙"}]}]
    items = _ths_phase_items(rows, "allotment")
    assert len(items) == 1
    assert items[0]["status"] == "won"
    assert items[0]["name"] == "申菱转债"


from execution.allotment import query_allotment


class _AllotGridUser:
    _main = None
    def __init__(self, rows):
        self._rows = rows

    def _switch_left_menus(self, path):
        pass

    def _get_grid_data(self, cid):
        return self._rows


def test_query_allotment_rejects_unreadable_grid(monkeypatch):
    import execution.ths_client as tc

    monkeypatch.setattr(tc, "read_grid_via_ocr", lambda *a, **k: None)
    user = _AllotGridUser([])
    with pytest.raises(RuntimeError, match="中签明细"):
        query_allotment(user)


def test_query_allotment_accepts_empty_and_valid(monkeypatch):
    import execution.ths_client as tc

    monkeypatch.setattr(tc, "read_grid_via_ocr", lambda *a, **k: [])
    assert query_allotment(_AllotGridUser([])) == []
    valid = [{"证券名称": "申菱转债", "证券代码": "127258", "中签数量": "10"}]
    monkeypatch.setattr(tc, "read_grid_via_ocr", lambda *a, **k: valid)
    assert query_allotment(_AllotGridUser([])) == valid

# AI-SUMMARY: 网格焦点/置前、xiadan 启动等待、补点重试、网格 OCR、历史行过滤测试
import execution.ths_client as tc


class _MainWin:
    handle = 777


class _CheckedGridUser:
    def __init__(self, pages):
        self._main = _MainWin()
        self.pages = list(pages)
        self.calls = 0

    def _get_grid_data(self, cid):
        self.calls += 1
        return self.pages.pop(0)


def test_read_grid_checked_retries_when_focus_fails():
    junk = [{"全部完成。汇总：": "## 交付清单"}]
    good = [{"证券名称": "申菱转债", "证券代码": "127258"}]
    user = _CheckedGridUser([junk, good])
    focused = []
    rows = tc.read_grid_checked(
        user, 1047, ("证券名称", "证券代码"),
        focus_fn=lambda main: focused.append(main.handle),
        sleep_fn=lambda _s: None,
    )
    assert rows == good
    assert focused == [777, 777]


def test_read_grid_checked_gives_up_after_attempts():
    junk = [{"全部完成。汇总：": "## 交付清单"}]
    user = _CheckedGridUser([junk, junk, junk, junk])
    rows = tc.read_grid_checked(
        user, 1047, ("证券名称",),
        focus_fn=lambda _m: None, sleep_fn=lambda _s: None,
    )
    assert rows == junk
    assert user.calls <= 3


import execution.ths_account_ui as tui
from shared.errors import AutoIpoError
import pytest


def test_xiadan_identity_waits_for_combo_init():
    ui = tui.ThsAccountUI.__new__(tui.ThsAccountUI)
    calls = {"n": 0}

    class _Combo:
        def window_text(self):
            return "平安证券-张*龙"

        def item_texts(self):
            return ["平安证券-张*龙"]

    def fake_main(_client):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("控件未找到")
        return object()

    ui.client = object()
    ui._main_window_fn = fake_main
    ui._control_id = lambda name: 1
    ui._require_unique_combo = lambda main, cid, name: _Combo()
    ui._combo_texts = lambda combo: ["平安证券-张*龙"]
    ui._current_value_fn = lambda client: "326219242115"
    ui._sleep = lambda _s: None

    present, current, display, labels = ui._xiadan_identity()
    assert present and current == "326219242115"
    assert calls["n"] == 3


def test_xiadan_identity_gives_up_bounded():
    ui = tui.ThsAccountUI.__new__(tui.ThsAccountUI)
    ui.client = object()
    ui._main_window_fn = lambda _c: (_ for _ in ()).throw(RuntimeError("控件未找到"))
    ui._control_id = lambda name: 1
    ui._sleep = lambda _s: None
    with pytest.raises(AutoIpoError):
        ui._xiadan_identity(max_wait_s=3, interval_s=1)


from tests.test_ths_account_ui import _ui


def test_reclick_recovers_when_first_click_not_effective():
    ui, state = _ui(current="9999999990", labels=("乙-9999999990",), switch_value="9999999990")
    state["rows"] = [{"index": 0, "text": "平安证券-程*宇", "top": 0}]
    ui._read_rows_fn = lambda _menu: list(state["rows"])
    clicks = {"n": 0}

    def click_row(_menu, _row, _total):
        clicks["n"] += 1
        if clicks["n"] >= 2:
            state["labels"] = ["平安证券-程*宇"]
            state["current"] = "326219242115"
            state["switch_value"] = "326219242115"

    ui._click_row_fn = click_row
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert clicks["n"] == 2, "首轮未生效必须补点一次"
    assert result.status in {"ready", "already_logged_in"}, f"补点后应登录成功，实际 {result.status}"


import shared.username_ocr as uo


def _item(text, left, top, right=None, bottom=None):
    return {
        "text": text,
        "left": float(left),
        "top": float(top),
        "right": float(right if right is not None else left + 60),
        "bottom": float(bottom if bottom is not None else top + 14),
    }


def test_grid_ocr_maps_columns_by_header():
    items = [
        _item("证券代码", 10, 0), _item("证券名称", 100, 0), _item("中签数量", 200, 0),
        _item("127258", 10, 20), _item("申菱转债", 100, 20), _item("10", 200, 20),
        _item("718150", 10, 40), _item("莱特发债", 100, 40), _item("10", 200, 40),
    ]
    rows = uo.grid_rows_from_items(items)
    stripped = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    assert stripped == [
        {"证券代码": "127258", "证券名称": "申菱转债", "中签数量": "10"},
        {"证券代码": "718150", "证券名称": "莱特发债", "中签数量": "10"},
    ]
    assert all("_top" in row and "_bottom" in row for row in rows)


def test_grid_ocr_none_when_no_header():
    assert uo.grid_rows_from_items([_item("杂项", 10, 10)], header_keys=("证券代码",)) is None


def test_allotment_filters_historical_rows():
    import execution.allotment as al
    import execution.ths_client as tc2
    from execution.ths_account_runner import default_account_task, ThsAccountTaskContext

    rows = [
        {"证券名称": "莱特发债", "证券代码": "718150", "中签日期": 20260930, "中签数量": 10},
        {"证券名称": "申菱转债", "证券代码": "127258", "中签日期": 20261021, "中签数量": 10},
    ]
    original = al.query_allotment
    orig_connect = tc2.connect
    import data_fetch.calendar as cal_mod
    orig_calendar = cal_mod.fetch_calendar_for
    try:
        al.query_allotment = lambda user: rows
        tc2.connect = lambda **kw: None
        # 2026-10-24 起过滤需当日申购代码：把 127258 视为 10-20 的申购标的
        cal_mod.fetch_calendar_for = lambda _day: {
            "day": _day, "new_stocks": [],
            "cbs": [{"name": "申菱转债", "code": "127258", "apply_code": "127258"}],
        }
        ctx = ThsAccountTaskContext(
            day="2026-10-20", live=False, mode="dry_run", phase="allotment",
            ths_username="mx_test", fund_account={"target_key": "f1"},
            client=None, cfg={"strategy": {"blacklist": []}},
        )
        result = default_account_task(ctx)
        names = [r.get("证券名称") for r in result.get("allotment", [])]
        assert "申菱转债" in names
        assert "莱特发债" not in names, "历史中签行必须按业务日+当日标的过滤"
    finally:
        al.query_allotment = original
        tc2.connect = orig_connect
        cal_mod.fetch_calendar_for = orig_calendar

# AI-SUMMARY: 宽松主窗识别尺寸下限——启动页/弹窗小窗不得误当主窗
import sys
import types

import execution.hexin_login as hl


def _install_fake_win32(monkeypatch, windows):
    def enum_windows(cb, _):
        for hwnd, pid, title, visible, class_name, rect in windows:
            cb(hwnd, None)

    fake_gui = types.SimpleNamespace(
        EnumWindows=enum_windows,
        IsWindowVisible=lambda hwnd: next(w[3] for w in windows if w[0] == hwnd),
        GetWindowText=lambda hwnd: next(w[2] for w in windows if w[0] == hwnd),
        GetClassName=lambda hwnd: next(w[4] for w in windows if w[0] == hwnd),
        GetWindowRect=lambda hwnd: next(w[5] for w in windows if w[0] == hwnd),
    )
    fake_process = types.SimpleNamespace(
        GetWindowThreadProcessId=lambda hwnd: (0, next(w[1] for w in windows if w[0] == hwnd))
    )
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)


def test_loose_fallback_skips_small_splash_window(monkeypatch):
    # (hwnd, pid, title, visible, class_name, rect)
    windows = [
        (100, 1234, "同花顺", True, "#32768", (0, 0, 400, 300)),      # 启动小窗
        (101, 1234, "同花顺 远航版", True, "#32768", (0, 0, 1920, 1080)),  # 主窗
    ]
    _install_fake_win32(monkeypatch, windows)
    monkeypatch.setattr(hl, "_hexin_pids", lambda client=None: {1234})
    assert hl.find_hexin_hwnd() == 101

# AI-SUMMARY: 信用账户"融"后缀 + xiadan 省略"证券"的身份归一化测试
from tests.test_ths_account_ui import _ui


def test_credit_rong_suffix_and_short_broker_name_match():
    """许*鸣融（信用融标记）点击后 xiadan 显示 中信建投-许*鸣，必须判为同一账户。"""
    ui, state = _ui(current="8888882440", labels=("中信建投-许*鸣",), switch_value="8888882440")
    state["rows"] = [{"index": 0, "text": "中信建投证券-许*鸣融", "top": 0}]
    ui._read_rows_fn = lambda _menu: list(state["rows"])
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status in {"ready", "already_logged_in"}, f"实际 {result.status}"

# AI-SUMMARY: 当日/未来日不得用 K 线判定（盘前无当日 K 线会误判非交易日）
from data_fetch.trading_days import is_trading_day
from datetime import date, timedelta


def test_today_weekday_is_trading_without_kline():
    today = date.today().isoformat()
    # 周末另行处理；这里只测工作日当日不查 K 线
    if date.today().weekday() < 5:
        assert is_trading_day(today) is True


def test_past_holiday_still_detected():
    assert is_trading_day("2026-10-01") is False  # 国庆（历史日，K线可靠）


def test_past_trading_day_true():
    assert is_trading_day("2026-10-20") is True


def test_weekend_false():
    assert is_trading_day("2026-10-24") is False  # 周六
