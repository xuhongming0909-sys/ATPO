# AI-SUMMARY: 订单台账测试——缺失才初始化，损坏/未知版本/写入失败全部 fail-closed
import json

import pytest

from execution.order_ledger import LEDGER_VERSION, OrderLedger
from shared.errors import AutoIpoError


def test_begin_once_then_block(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    order = {"apply_code": "371175", "name": "中科转债"}
    assert ledger.begin("甲", order) is True
    assert ledger.begin("甲", order) is False
    assert ledger.get("甲", order["apply_code"])["status"] == "unknown"


def test_status_persists_across_instances(tmp_path):
    order = {"apply_code": "783000", "name": "测试沪债"}
    first = OrderLedger("2026-10-19", root=tmp_path)
    first.begin("乙", order)
    first.mark("乙", order, "submitted_unverified", reason="F8 查询失败")
    second = OrderLedger("2026-10-19", root=tmp_path)
    assert second.begin("乙", order) is False
    assert second.get("乙", "783000")["status"] == "submitted_unverified"


def test_ledger_does_not_store_fund_account(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    ledger.begin("丙", {"apply_code": "001381", "name": "测试科技", "fund_account": "1234567890"})
    raw = ledger.path.read_text(encoding="utf-8")
    assert "1234567890" not in raw


def test_same_account_hash_is_blocked_across_clients(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    order = {"apply_code": "371175", "name": "中科转债"}
    assert ledger.begin("甲", order, account_key="hash-a", client_id="ths1") is True
    assert ledger.begin("别名甲", order, account_key="hash-a", client_id="ths2") is False


def test_different_account_hashes_are_independent(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    order = {"apply_code": "371175", "name": "中科转债"}
    assert ledger.begin("甲", order, account_key="hash-a", client_id="ths1") is True
    assert ledger.begin("乙", order, account_key="hash-b", client_id="ths2") is True


def test_client_id_is_diagnostic_only_and_no_fund_account_is_saved(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    ledger.begin("甲", {"apply_code": "001381", "name": "测试", "fund_account": "1234567890"},
                 account_key="hash-a", client_id="ths2")
    raw = ledger.path.read_text(encoding="utf-8")
    assert '"client_id": "ths2"' in raw
    assert "1234567890" not in raw


def test_missing_file_is_initialized_only(tmp_path):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    payload = json.loads(ledger.path.read_text(encoding="utf-8"))
    assert payload == {"version": LEDGER_VERSION, "day": "2026-10-19", "orders": {}}


def test_corrupt_file_is_preserved_and_fail_closed(tmp_path):
    path = tmp_path / "2026-10-19.json"
    raw = b"{broken"
    path.write_bytes(raw)
    with pytest.raises(AutoIpoError) as excinfo:
        OrderLedger("2026-10-19", root=tmp_path)
    assert excinfo.value.code == "ORDER_LEDGER_CORRUPT"
    assert path.read_bytes() == raw


def test_unknown_version_is_preserved_and_fail_closed(tmp_path):
    path = tmp_path / "2026-10-19.json"
    raw = '{"version": 99, "orders": {}}'
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(AutoIpoError) as excinfo:
        OrderLedger("2026-10-19", root=tmp_path)
    assert excinfo.value.code == "ORDER_LEDGER_VERSION_UNKNOWN"
    assert path.read_text(encoding="utf-8") == raw


def test_write_failure_blocks_begin_and_preserves_existing_file(tmp_path, monkeypatch):
    ledger = OrderLedger("2026-10-19", root=tmp_path)
    before = ledger.path.read_bytes()

    def fail_replace(_self, _target):
        raise OSError("disk full")

    monkeypatch.setattr("pathlib.Path.replace", fail_replace)
    with pytest.raises(AutoIpoError) as excinfo:
        ledger.begin("甲", {"apply_code": "371175", "name": "中科转债"})
    assert excinfo.value.code == "ORDER_LEDGER_WRITE_FAILED"
    assert ledger.path.read_bytes() == before
    with pytest.raises(AutoIpoError):
        ledger.begin("甲", {"apply_code": "783000", "name": "另一只"})