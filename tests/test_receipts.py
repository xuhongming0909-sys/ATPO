# AI-SUMMARY: 登录/申购/中签标准回执测试——时间+账户+事件全量渲染、凭据排除、开关与注入
from datetime import datetime

import pytest

NOW = datetime(2026, 10, 17, 10, 5, 33)


def test_render_login_receipt_time_account_event():
    from notification.receipts import render_receipt

    title, body = render_receipt("login", {
        "date": "2026-10-17",
        "clients": [
            {"id": "mx_525378109", "accounts": [
                {"display_name": "平安证券-张*龙", "fund_account": "326219248611",
                 "ths_account": "mx_525378109", "login_status": "ready", "status": "completed"},
                {"display_name": "华宝证券-蔡*良", "fund_account": "88011223344",
                 "ths_account": "mx_525378109", "login_status": "dialog_required",
                 "dialog_required": True},
            ]},
        ],
    }, now=NOW)
    assert title == "[登录回执][10/17 10:05] 成功 1｜需人工 1｜失败 0"
    assert "日期：2026-10-17" in body
    assert "时间：2026-10-17 10:05:33" in body
    # 时间+账户+事件：完整资金账号、显示名、THS 用户名全部可见
    assert "账户：平安证券-张*龙｜资金账号：326219248611｜THS：mx_525378109｜事件：登录成功" in body
    assert "账户：华宝证券-蔡*良｜资金账号：88011223344｜THS：mx_525378109｜事件：需人工处理" in body
    assert "下一步：" in body


def test_login_manual_and_failed_statuses():
    from notification.receipts import render_receipt

    title, body = render_receipt("login", {
        "date": "2026-10-17",
        "clients": [{"client_id": "mx_1", "accounts": [
            {"display_name": "平安证券-张*龙", "login_status": "manual_required",
             "manual_required": True, "detail": "安全验证弹窗"},
            {"display_name": "平安证券-李*明", "login_status": "xiadan_failed"},
        ]}],
    }, now=NOW)
    assert title == "[登录回执][10/17 10:05] 成功 0｜需人工 1｜失败 1"
    assert "安全验证弹窗" in body
    assert "事件：登录失败" in body


def test_render_subscribe_receipt_full_fields():
    from notification.receipts import render_receipt

    title, body = render_receipt("subscribe", {
        "date": "2026-10-17",
        "summary": {"success": 1, "skipped": 1, "failed": 0},
        "items": [
            {"account": "平安证券-张*龙", "fund_account": "326219248611", "ths_account": "mx_1",
             "name": "中科转债", "apply_code": "371175", "amount": 10000, "unit": "张",
             "status": "submitted"},
            {"account": "华宝证券-蔡*良", "name": "测试科技", "apply_code": "001381",
             "amount": 500, "unit": "股", "status": "skipped", "reason": "无申购额度"},
        ],
        "next_action": "失败项人工核对当日委托，禁止重复提交。",
    }, now=NOW)
    assert title == "[申购回执][10/17 10:05] 成功 1｜跳过 1｜失败 0"
    assert "日期：2026-10-17" in body
    assert "账户：平安证券-张*龙｜资金账号：326219248611｜THS：mx_1｜申购：中科转债（371175）｜数量：10000 张｜状态：submitted" in body
    assert "失败原因：无申购额度" in body
    assert "下一步：失败项人工核对当日委托，禁止重复提交。" in body


def test_render_allotment_win_and_no_win_titles():
    from notification.receipts import render_receipt

    won_title, won_body = render_receipt("allotment", {
        "date": "2026-10-17",
        "items": [
            {"account": "平安证券-张*龙", "fund_account": "326219248611", "name": "华纬转债",
             "apply_code": "111000", "winning_qty": 10, "payment_amount": 1000, "status": "won"},
        ],
        "next_action": "请按缴款截止时间处理。",
    }, now=NOW)
    no_title, _no_body = render_receipt("allotment", {"date": "2026-10-17", "items": []}, now=NOW)
    assert won_title == "[中签回执][10/17 10:05] 中签 1 户"
    assert "账户：平安证券-张*龙｜资金账号：326219248611｜中签：华纬转债（111000）｜中签数量：10｜缴款金额：1000 元" in won_body
    assert "缴款提醒：中签账户请在缴款截止时间前确保可用资金足额。" in won_body
    assert no_title == "[中签回执][10/17 10:05] 无中签"


def test_allotment_unpublished_is_not_final_no_win():
    from notification.receipts import render_receipt

    title, body = render_receipt("allotment", {
        "date": "2026-10-17",
        "summary": {"data_unpublished": True},
        "items": [],
    }, now=NOW)
    assert title == "[中签回执][10/17 10:05] 无中签"
    assert "数据未公布，将继续补查" in body
    assert "下一步：数据未公布，将继续补查。" in body


def test_dialog_closed_counts_as_manual_not_failed():
    from notification.receipts import render_receipt

    title, _body = render_receipt("login", {
        "date": "2026-10-17",
        "clients": [{"id": "mx_1", "accounts": [
            {"display_name": "平安证券-张*龙", "login_status": "dialog_closed"},
        ]}],
    }, now=NOW)
    assert title == "[登录回执][10/17 10:05] 成功 0｜需人工 1｜失败 0"


def test_render_keeps_account_and_masks_credentials():
    from notification.receipts import render_receipt

    _, body = render_receipt("subscribe", {
        "date": "2026-10-17",
        "items": [{"account": "张*龙", "status": "failed",
                   "reason": "sendkey=SCT1234567890abcdef captcha：9565 资金账号 326219248611"}],
    }, now=NOW)
    assert "SCT1234567890abcdef" not in body
    assert "9565" not in body
    assert "326219248611" in body  # 资金账号完整保留


def test_all_three_kinds_always_render_next_action():
    from notification.receipts import render_receipt

    for kind, data in (
        ("login", {"date": "2026-10-17", "clients": []}),
        ("subscribe", {"date": "2026-10-17", "items": []}),
        ("allotment", {"date": "2026-10-17", "items": []}),
    ):
        title, body = render_receipt(kind, data, now=NOW)
        assert title.startswith("[")
        assert "日期：2026-10-17" in body
        assert "下一步：" in body


def test_send_receipt_accepts_injected_config_and_sender():
    import unittest.mock

    import notification.receipts as receipts

    calls = []
    with unittest.mock.patch.object(receipts.serverchan, "send",
                                    side_effect=AssertionError("不得走真实通道")):
        result = receipts.send_receipt(
            "subscribe", {"date": "2026-10-17", "items": []},
            config={"notification_receipts": {"send_subscribe": True}},
            sender=lambda title, body: calls.append((title, body)) or {"code": 0},
        )
    assert result["sent"] is True
    assert len(calls) == 1


def test_login_receipt_counts_unique_fund_accounts_dynamically():
    from notification.receipts import render_receipt

    accounts = []
    for i in range(13):
        accounts.append({
            "account_key": f"fund-{i:02d}",
            "account": f"账户{i + 1:02d}",
            "display_name": f"券商-户{i + 1:02d}",
            "ths_account": "mx_test",
            "fund_account": f"32621924{i:04d}",
            "login_status": "dialog_closed" if i == 12 else "ready",
        })
    clients = [
        {"id": "mx_test", "accounts": accounts[:7]},
        {"id": "mx_test", "accounts": accounts[7:] + [dict(accounts[0])]},
    ]
    title, body = render_receipt("login", {"date": "2026-10-18", "clients": clients}, now=NOW)
    assert title == "[登录回执][10/18 10:05] 成功 12｜需人工 1｜失败 0"  # 重复行按 account_key 去重
    assert "资金账号：326219240000" in body
    assert "THS：mx_test" in body
