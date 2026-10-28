# AI-SUMMARY: 定时任务编排——打新日历抓取（当日+明日合并为一条推送、内部分段）、消息格式化与推送
# 抓取失败重试一次，再失败推「日历抓取失败」告警（不能让定时任务静默死）
import time
from datetime import date, timedelta

from data_fetch.calendar import fetch_calendar_for
from notification import serverchan
from shared.config import load_config

WEEKDAYS_CN = "一二三四五六日"


def _num(value):
    """东财接口偶发返回字符串数字，统一强转 float，失败归 None。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_money_wan(value) -> str:
    v = _num(value)
    return f"{v:g} 万" if v is not None else "待定"


def _top_limit(item: dict) -> str:
    """顶格申购数量展示：可转债固定 1 万张；新股取申购上限（股）。"""
    if item["kind"] == "可转债":
        return "1万张"
    limit = _num(item.get("apply_limit"))
    return f"{limit / 10000:g}万股" if limit else "待定"


def _weekday(day: str) -> str:
    return "周" + WEEKDAYS_CN[date.fromisoformat(day).weekday()]


def _day_segment(cal: dict) -> str:
    """标题中的单日片段：`10/15 华纬转债 1万张、...`，无标的返回空串。"""
    items = cal["cbs"] + cal["new_stocks"]
    if not items:
        return ""
    label = cal["day"][5:].replace("-", "/")
    return f"{label} " + "、".join(f"{i['name']} {_top_limit(i)}" for i in items)


def _make_title(today: dict, tomorrow: dict) -> str:
    """标题承载核心信息：两日分段用「；」连接；超长折叠为「债 N 股 M」。"""
    segments = [s for s in (_day_segment(today), _day_segment(tomorrow)) if s]
    if not segments:
        return f"{today['day'][5:].replace('-', '/')} 今明无可申购标的"
    joined = "；".join(segments)
    if len(joined) <= 34:
        return joined
    items = today["cbs"] + today["new_stocks"] + tomorrow["cbs"] + tomorrow["new_stocks"]
    n_cb = sum(1 for i in items if i["kind"] == "可转债")
    return f"今明打新{len(items)}只：债 {n_cb} 股 {len(items) - n_cb}"


def _section(label: str, cal: dict) -> list[str]:
    lines = [f"## {label}（{cal['day'][5:]} {_weekday(cal['day'])}）\n"]
    for c in cal["cbs"]:
        scale = f"{c['issue_scale_yi']:g} 亿" if c["issue_scale_yi"] else "规模待定"
        lines.append(
            f"- **{c['name']}**（`{c['apply_code']}`）顶格 {_top_limit(c)}"
            f"｜评级 {c['rating'] or '未定'}｜{scale}｜正股 {c['stock_name'] or '-'}"
        )
    for s in cal["new_stocks"]:
        lines.append(
            f"- **{s['name']}**（`{s['apply_code']}`）顶格 {_top_limit(s)}"
            f"｜{s['market']}｜顶格需市值 {_fmt_money_wan(s['top_marketcap_wan'])}"
        )
    if not cal["cbs"] and not cal["new_stocks"]:
        lines.append("无可申购标的。")
    return lines


def format_daily_report(today: dict, tomorrow: dict) -> tuple[str, str]:
    """当日+明日合并为一条消息，正文分「今日」「明日」两段。"""
    title = _make_title(today, tomorrow)
    lines = _section("今日", today)
    lines.append("")
    lines += _section("明日", tomorrow)
    lines.append("\n> 中签后 T+2 日 16:00 前须足额缴款，弃购 3 次限制打新 6 个月。")
    return title, "\n".join(lines)


def daily_report(day: str | None = None, push: bool = True, _fetcher=None) -> list[tuple[str, str]]:
    """抓取当日+明日日历，合并为一条推送；两日皆空则跳过（受 skip_push_when_empty 控制）。"""
    fetch = _fetcher or fetch_calendar_for
    today_str = day or date.today().isoformat()
    tomorrow_str = (date.fromisoformat(today_str) + timedelta(days=1)).isoformat()
    try:
        today, tomorrow = fetch(today_str), fetch(tomorrow_str)
    except Exception:
        time.sleep(30)  # 网络抖动重试一次
        try:
            today, tomorrow = fetch(today_str), fetch(tomorrow_str)
        except Exception as e:
            if push:
                serverchan.send("打新日历抓取失败", f"{today_str} 日历连续两次抓取失败：{str(e)[:150]}")
            raise
    empty = not (today["new_stocks"] or today["cbs"] or tomorrow["new_stocks"] or tomorrow["cbs"])
    cfg = load_config()
    if empty and cfg.get("notification", {}).get("skip_push_when_empty", True):
        return []
    title, body = format_daily_report(today, tomorrow)
    if push:
        serverchan.send(title, body)
    return [(title, body)]
