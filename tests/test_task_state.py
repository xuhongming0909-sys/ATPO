# AI-SUMMARY: 任务状态测试——持久化、幂等和敏感字段脱敏
from datetime import datetime

from shared.task_state import TaskStateStore, sanitize


def test_task_state_round_trip_and_idempotence(tmp_path):
    store = TaskStateStore(tmp_path / "task_state.json")
    item = store.record("subscribe", "2026-10-17", "completed", receipt_status="sent",
                        mode="live", payload={"status": "submitted"})
    assert store.get("subscribe", "2026-10-17", "live") == item
    assert store.should_skip("subscribe", "2026-10-17", "live") is not None

    store.record("subscribe", "2026-10-17", "retryable", receipt_status="failed", mode="live")
    assert store.get("subscribe", "2026-10-17", "live").status == "retryable"
    assert store.should_skip("subscribe", "2026-10-17", "live") is None


def test_task_state_separates_dry_run_and_sanitizes(tmp_path):
    store = TaskStateStore(tmp_path / "task_state.json")
    store.record("subscribe", "2026-10-17", "completed", receipt_status="not_required", mode="dry_run")
    assert store.get("subscribe", "2026-10-17", "live") is None

    item = store.record("allotment", "2026-10-17", "retryable", error="资金账号 326219248611 密码：top-secret 验证码=9565",
                        payload={"fund_account": "326219248611", "captcha": "9565", "name": "张*龙"})
    assert "326219248611" in item.sanitized_error  # 资金账号完整保留（本机自用）
    assert "***" in item.sanitized_error
    assert item.payload["fund_account"] == "326219248611"
    assert item.payload["captcha"] == "***"
    assert item.payload["name"] == "张*龙"


def test_task_state_completed_at_is_recorded(tmp_path):
    store = TaskStateStore(tmp_path / "task_state.json")
    item = store.record("daily_report", "2026-10-17", "completed", receipt_status="not_required")
    assert datetime.fromisoformat(item.completed_at)


def test_sanitize_masks_credentials_in_free_text():
    text = sanitize("fund_account=326219248611 password: top-secret captcha：9565")
    assert "326219248611" in text  # 资金账号完整保留
    assert "top-secret" not in text
    assert "9565" not in text


def test_sanitize_keeps_full_ths_username():
    assert sanitize({"account": "mx_525378109"})["account"] == "mx_525378109"
    assert sanitize("account=mx_525378109 status=wrong_account") == \
           "account=mx_525378109 status=wrong_account"


import unittest

from shared.task_state import result_signature


class ResultSignatureTests(unittest.TestCase):
    def test_signature_key_order_stable_and_detects_change(self):
        base = {"items": [{"account": "张*龙", "apply_code": "111000", "winning_qty": 10}]}
        same = {"items": [{"winning_qty": 10, "apply_code": "111000", "account": "张*龙"}]}
        changed = {"items": [{"account": "张*龙", "apply_code": "111000", "winning_qty": 11}]}
        self.assertEqual(result_signature(base), result_signature(same))
        self.assertNotEqual(result_signature(base), result_signature(changed))

    def test_signature_uses_full_fund_account(self):
        # 不脱敏后，不同资金账号必须产生不同指纹
        self.assertNotEqual(result_signature({"account": "326219248611"}),
                            result_signature({"account": "326000008611"}))


