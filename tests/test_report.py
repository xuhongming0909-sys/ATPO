# AI-SUMMARY: 推送消息格式化测试（单条推送，今日/明日分段）
from data_fetch.calendar import parse_new_stock, parse_cb
from scheduler.jobs import format_daily_report, daily_report
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _empty(day):
    return {"day": day, "new_stocks": [], "cbs": []}


def test_format_title_two_days_one_message():
    today = {"day": "2026-10-15", "new_stocks": [], "cbs": [parse_cb(load("cb_item.json"))]}
    tomorrow = {"day": "2026-10-16", "new_stocks": [parse_new_stock(load("ipo_item.json"))], "cbs": []}
    title, body = format_daily_report(today, tomorrow)
    assert "10/15 中科转债 1万张" in title
    assert "10/16 测试科技 1.35万股" in title
    assert "；" in title                    # 两段之间用分号分隔
    assert "今日" in body and "明日" in body
    assert "371175" in body and "001381" in body


def test_title_collapses_when_many_items():
    day_cal = {
        "day": "2026-10-16",
        "new_stocks": [parse_new_stock(load("ipo_item.json"))] * 5,
        "cbs": [parse_cb(load("cb_item.json"))] * 5,
    }
    title, _ = format_daily_report(day_cal, day_cal)
    assert "债 10" in title and "股 10" in title
    assert "中科转债" not in title


def test_daily_report_skips_when_both_empty():
    msgs = daily_report(day="2026-10-17", push=False, _fetcher=_empty)
    assert msgs == []


def test_daily_report_single_message():
    def fetcher(day):
        if day == "2026-10-15":
            return {"day": day, "new_stocks": [], "cbs": [parse_cb(load("cb_item.json"))]}
        return _empty(day)
    msgs = daily_report(day="2026-10-15", push=False, _fetcher=fetcher)
    assert len(msgs) == 1                    # 一条推送，内部分段
    assert "10/15 中科转债 1万张" in msgs[0][0]
