# AI-SUMMARY: 定时任务编排——每日打新日历抓取、消息格式化与推送
from datetime import date

from data_fetch.calendar import fetch_calendar_for
from notification import serverchan
from shared.config import load_config

WEEKDAYS_CN = "一二三四五六日"


def _fmt_money_wan(value) -> str:
    return f"{value:g} 万" if value is not None else "待定"


def format_daily_report(cal: dict) -> tuple[str, str]:
    day = cal["day"]
    d = date.fromisoformat(day)
    stocks, cbs = cal["new_stocks"], cal["cbs"]
    total = len(stocks) + len(cbs)
    title = f"打新日历 {day}（周{WEEKDAYS_CN[d.weekday()]}）{total} 只"

    lines: list[str] = []
    if cbs:
        lines.append(f"## 可转债 {len(cbs)} 只\n")
        for c in cbs:
            scale = f"{c['issue_scale_yi']:g} 亿" if c["issue_scale_yi"] else "规模待定"
            lines.append(
                f"- **{c['name']}**（申购代码 `{c['apply_code']}`）"
                f"｜评级 {c['rating'] or '未定'}｜{scale}｜正股 {c['stock_name'] or '-'}"
            )
    if stocks:
        lines.append(f"\n## 新股 {len(stocks)} 只\n")
        for s in stocks:
            lines.append(
                f"- **{s['name']}**（申购代码 `{s['apply_code']}`）"
                f"｜{s['market']}｜上限 {s['apply_limit'] or '?'} 股"
                f"｜顶格需市值 {_fmt_money_wan(s['top_marketcap_wan'])}"
            )
    if not lines:
        lines.append("今日无可申购的新股/可转债。")

    lines.append("\n> 中签后 T+2 日 16:00 前须足额缴款，弃购 3 次限制打新 6 个月。")
    return title, "\n".join(lines)


def daily_report(day: str | None = None, push: bool = True) -> tuple[str, str]:
    day = day or date.today().isoformat()
    cal = fetch_calendar_for(day)
    title, body = format_daily_report(cal)
    empty = not cal["new_stocks"] and not cal["cbs"]
    cfg = load_config()
    skip_empty = cfg.get("notification", {}).get("skip_push_when_empty", True)
    if push and not (empty and skip_empty):
        serverchan.send(title, body)
    return title, body
