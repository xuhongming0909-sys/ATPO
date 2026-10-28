# AI-SUMMARY: 日历解析层测试（fixture 来自东财真实接口响应 2026-10-15）
import json
from pathlib import Path

import pytest

from data_fetch.calendar import parse_new_stock, parse_cb, fetch_calendar_for, _query

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_new_stock():
    item = parse_new_stock(load("ipo_item.json"))
    assert item["kind"] == "新股"
    assert item["code"] == "001381"
    assert item["apply_code"] == "001381"
    assert item["name"] == "测试科技"
    assert item["market"] == "深交所其他"
    assert item["apply_date"] == "2026-10-19"
    assert item["apply_limit"] == 13500
    assert item["top_marketcap_wan"] == 13.5
    assert item["ballot_pay_date"] == "2026-10-21"


def test_parse_cb():
    item = parse_cb(load("cb_item.json"))
    assert item["kind"] == "可转债"
    assert item["code"] == "123289"
    assert item["apply_code"] == "371175"
    assert item["name"] == "中科转债"
    assert item["rating"] == "AA+"
    assert item["issue_scale_yi"] == 10
    assert item["stock_name"] == "中科环保"
    assert item["apply_date"] == "2026-10-16"


def test_fetch_calendar_for_separates_kinds():
    day = "2026-10-16"
    cal = fetch_calendar_for(day, _fetchers={
        "new_stocks": lambda d: [parse_new_stock(load("ipo_item.json"))],
        "cbs": lambda d: [parse_cb(load("cb_item.json"))],
    })
    assert cal["day"] == day
    assert len(cal["new_stocks"]) == 1
    assert len(cal["cbs"]) == 1


def test_empty_api_result_is_not_an_error(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "result": None, "code": 9201, "message": "查询数据为空"}

    monkeypatch.setattr("data_fetch.calendar.requests.get", lambda *_a, **_k: Response())
    assert _query("RPTA_APP_IPOAPPLY", "APPLY_DATE", "2026-10-19") == []


def test_real_api_failure_is_not_treated_as_empty_calendar(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "result": None, "code": 500, "message": "服务异常"}

    monkeypatch.setattr("data_fetch.calendar.requests.get", lambda *_a, **_k: Response())
    with pytest.raises(RuntimeError, match="服务异常"):
        _query("RPTA_APP_IPOAPPLY", "APPLY_DATE", "2026-10-19")
def test_fetch_calendar_for_caches_per_day(monkeypatch):
    import data_fetch.calendar as cal

    cal._DAY_CACHE.clear()
    calls = []
    monkeypatch.setattr(cal, "fetch_new_stocks", lambda day: calls.append(("s", day)) or [])
    monkeypatch.setattr(cal, "fetch_cbs", lambda day: calls.append(("c", day)) or [])
    first = cal.fetch_calendar_for("2026-10-22")
    second = cal.fetch_calendar_for("2026-10-22")
    assert first is second
    assert calls == [("s", "2026-10-22"), ("c", "2026-10-22")]
    cal._DAY_CACHE.clear()
