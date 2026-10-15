# AI-SUMMARY: CLI 统一入口（calendar 查看日历 / notify-test 通道测试 / daily-report 每日推送）
import argparse
import json
from datetime import date

from data_fetch.calendar import fetch_calendar_for
from notification import serverchan
from scheduler.jobs import daily_report


def main():
    parser = argparse.ArgumentParser(prog="auto-ipo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("calendar", help="抓取并打印打新日历")
    sub.add_parser("notify-test", help="发送 Server酱 测试消息")
    sub.add_parser("daily-report", help="抓取当日日历并推送（空日历按配置跳过）")
    for name in ("calendar", "daily-report"):
        sub.choices[name].add_argument("--day", default=None, help="YYYY-MM-DD，默认今天")
    args = parser.parse_args()

    if args.cmd == "calendar":
        day = args.day or date.today().isoformat()
        print(json.dumps(fetch_calendar_for(day), ensure_ascii=False, indent=2))
    elif args.cmd == "notify-test":
        result = serverchan.send("自动打新 · 通道测试", "notify-test 推送成功。")
        print("推送成功, pushid:", result["data"]["pushid"])
    elif args.cmd == "daily-report":
        title, body = daily_report(day=args.day)
        print(title)
        print(body)


if __name__ == "__main__":
    main()
