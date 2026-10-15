# AI-SUMMARY: 推送消息格式化测试
from data_fetch.calendar import parse_new_stock, parse_cb
from scheduler.jobs import format_daily_report
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_format_with_items():
    cal = {
        "day": "2026-10-16",
        "new_stocks": [parse_new_stock(load("ipo_item.json"))],
        "cbs": [parse_cb(load("cb_item.json"))],
    }
    title, body = format_daily_report(cal)
    assert "2026-10-16" in title
    assert "中科转债" in body
    assert "371175" in body          # 申购代码必须出现
    assert "测试科技" in body
    assert "001381" in body


def test_format_empty():
    cal = {"day": "2026-10-17", "new_stocks": [], "cbs": []}
    title, body = format_daily_report(cal)
    assert "无" in body
