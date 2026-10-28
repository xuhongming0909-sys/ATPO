# AI-SUMMARY: 实盘安全测试——单次提交、重复阻断、批量 F8 核验和时段保护
import pytest

from execution.order_ledger import OrderLedger
from execution.subscribe import execute, live_run_allowed


CB = {"kind": "可转债", "name": "中科转债", "apply_code": "371175",
      "price": 100.0, "amount": 10000, "unit": "张"}


class _User:
    def __init__(self, error=None, rows=()):
        self.error = error
        self.rows = list(rows)
        self.calls = 0

    def buy(self, code, price, amount):
        self.calls += 1
        if self.error:
            raise self.error
        return {"entrust_no": "E1"}

    @property
    def today_entrusts(self):
        return list(self.rows)


def test_execute_never_retries_uncertain_submit(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    user = _User(error=RuntimeError("点击后窗口无响应"))
    results = execute(user, [CB], "live", ledger=ledger, account_id="甲")
    assert results[0]["status"] == "unknown"
    assert user.calls == 1
    again = execute(user, [CB], "live", ledger=ledger, account_id="甲")
    assert again[0]["status"] == "skipped"
    assert user.calls == 1


def test_execute_marks_submitted_unverified_when_f8_missing(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    user = _User(rows=[])
    results = execute(user, [CB], "live", ledger=ledger, account_id="甲")
    assert results[0]["status"] == "submitted_unverified"
    assert execute(user, [CB], "live", ledger=ledger, account_id="甲")[0]["status"] == "skipped"


def test_live_run_allowed_only_in_subscription_window():
    import datetime as dt
    day = dt.date(2026, 10, 19).isoformat()
    assert live_run_allowed(day, now=dt.datetime(2026, 10, 19, 10, 0))
    assert not live_run_allowed(day, now=dt.datetime(2026, 10, 19, 15, 1))
    assert not live_run_allowed("2026-10-18", now=dt.datetime(2026, 10, 19, 10, 0))


def test_force_retry_ledger_allows_explicit_repeat(tmp_path):
    ledger = OrderLedger("2026-10-22", root=tmp_path, allow_repeat=True)
    assert ledger.begin("甲", CB) is True
    assert ledger.begin("甲", CB) is True
    assert ledger.get("甲", CB["apply_code"])["attempt_count"] == 2


