# AI-SUMMARY: 申购执行单测——allowlist 生成、execute 台账/核验语义、uncovered_orders、live_run_allowed
from datetime import datetime, time as dtime

from execution.subscribe import (
    calendar_allowlist,
    execute,
    live_run_allowed,
    uncovered_orders,
    verify_entrust,
)


def _cal():
    return {
        "day": "2026-10-20",
        "cbs": [{"kind": "可转债", "name": "华纬转债", "apply_code": "071123", "code": "127123",
                 "rating": "AA", "issue_scale_yi": 3.2, "stock_name": "华纬科技"}],
        "new_stocks": [{"kind": "新股", "name": "测试新股", "apply_code": "301999", "code": "301999",
                        "market": "创业板", "apply_limit": 5000, "issue_price": 10.0,
                        "top_marketcap_wan": 12.0}],
    }


def test_calendar_allowlist_cb_top_and_new_stock():
    orders = calendar_allowlist(_cal())
    assert len(orders) == 2
    cb = next(o for o in orders if o["kind"] == "可转债")
    assert (cb["amount"], cb["unit"], cb["price"]) == (10000, "张", 100.0)
    stock = next(o for o in orders if o["kind"] == "新股")
    assert stock["amount"] == 5000 and stock["unit"] == "股"


def test_calendar_allowlist_blacklist_excludes_code():
    orders = calendar_allowlist(_cal(), blacklist=[{"apply_code": "071123"}])
    assert all(o["apply_code"] != "071123" for o in orders)


def test_calendar_allowlist_skips_unknown_price_or_limit():
    cal = _cal()
    cal["new_stocks"][0].pop("issue_price")
    orders = calendar_allowlist(cal)
    stock = next(o for o in orders if o["kind"] == "新股")
    assert stock["status"] if False else stock.get("skip") is True


def test_execute_dry_run_marks_all_dry_run():
    orders = calendar_allowlist(_cal())
    results = execute(None, orders, "dry_run")
    assert all(r["status"] == "dry_run" for r in results)


def test_execute_skips_bse_codes_on_form():
    orders = [{"apply_code": "920001", "name": "北交新股", "price": 5.0, "amount": 100, "unit": "股"}]
    user = object()
    results = execute(user, orders, "live", ledger=None)
    assert results[0]["status"] == "skipped"
    assert results[0]["error_code"] == "BSE_SINGLE_FORM_UNSUPPORTED"


def test_execute_ledger_blocks_repeat_attempt():
    orders = [{"apply_code": "071123", "name": "华纬转债", "price": 100.0, "amount": 10000, "unit": "张"}]

    class Ledger:
        def begin(self, account_id, order, **kw):
            return False

        def get(self, account_id, apply_code, **kw):
            return {"status": "submitted"}

    results = execute(object(), orders, "live", ledger=Ledger())
    assert results[0]["status"] == "skipped"
    assert results[0]["error_code"] == "ORDER_ALREADY_ATTEMPTED"


def test_verify_entrust_matches_unique_row():
    order = {"apply_code": "071123", "name": "华纬转债", "amount": 10000, "unit": "张"}
    rows = [{"证券代码": "071123", "证券名称": "华纬转债", "委托数量": 10000, "委托状态": "已报"}]
    assert verify_entrust(object(), order, entrust_rows=rows) is True


def test_verify_entrust_rejects_mismatch_qty():
    order = {"apply_code": "071123", "name": "华纬转债", "amount": 10000, "unit": "张"}
    rows = [{"证券代码": "071123", "证券名称": "华纬转债", "委托数量": 5000, "委托状态": "已报"}]
    assert verify_entrust(object(), order, entrust_rows=rows) is False


def test_uncovered_orders_excludes_covered():
    orders = [{"apply_code": "071123", "name": "华纬转债"}, {"apply_code": "301999", "name": "测试新股"}]
    batch = [{"apply_code": "071123", "name": "华纬转债", "status": "submitted"}]
    rest = uncovered_orders(orders, batch)
    assert [o["apply_code"] for o in rest] == ["301999"]


def test_live_run_allowed_requires_same_day_and_window(monkeypatch):
    cfg_holder = {"schedule": {"subscribe_window": ["09:30", "15:00"]}}
    import shared.config as config_mod
    monkeypatch.setattr(config_mod, "load_config", lambda: cfg_holder)
    day = "2026-10-20"
    assert live_run_allowed(day, now=datetime(2026, 10, 20, 10, 0)) is True
    assert live_run_allowed(day, now=datetime(2026, 10, 20, 16, 0)) is False
    assert live_run_allowed(day, now=datetime(2026, 10, 21, 10, 0)) is False
