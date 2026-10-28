# AI-SUMMARY: 批量申购安全测试——仅 calendar allowlist 且非 blacklist 可提交，未知/歧义整批拒绝
import execution.ipo_page as ipo
from execution.order_ledger import OrderLedger


class _User:
    def __init__(self, rows=None, query_error=None):
        self.rows = rows
        self.query_error = query_error
        self.submit_calls = 0

    def _handle_pop_dialogs(self):
        self.submit_calls += 1
        return {"message": "success"}

    def _switch_left_menus(self, path):
        if self.query_error:
            raise self.query_error


def _grid():
    return [
        {"新股名称": "中科转债", "新股代码": "371175", "申购数量": "10000"},
        {"新股名称": "黑名单", "新股代码": "111111", "申购数量": "1000"},
        {"新股名称": "无额度", "新股代码": "222222", "申购数量": "0"},
    ]


def _allowlist():
    return [
        {"name": "中科转债", "apply_code": "371175", "permissions": []},
        {"name": "黑名单", "apply_code": "111111"},
        {"name": "无额度", "apply_code": "222222"},
    ]


def _patch_ui(monkeypatch):
    import execution.ths_client as tc
    clicks = {"deselect": [], "buttons": []}
    monkeypatch.setattr(tc, "read_grid_via_ocr", lambda user, *a, **k: list(user.rows or []))
    monkeypatch.setattr(ipo, "read_ipo_grid", lambda _user: _grid())
    monkeypatch.setattr(ipo, "_click_button", lambda _u, control_id: clicks["buttons"].append(control_id))
    monkeypatch.setattr(ipo, "_click_grid_row", lambda _u, row_idx: clicks["deselect"].append(row_idx))
    return clicks


def test_only_allowlisted_nonblacklisted_rows_submit(monkeypatch, tmp_path):
    clicks = _patch_ui(monkeypatch)
    user = _User(rows=[{"证券代码": "371175", "证券名称": "中科转债"}])
    results = ipo.batch_subscribe(
        user,
        ledger=OrderLedger("2026-10-19", root=tmp_path),
        account_id="甲",
        allowlist=_allowlist(),
        blacklist=["111111"],
    )
    by_code = {r["apply_code"]: r for r in results}
    assert by_code["371175"]["status"] == "submitted"
    assert by_code["371175"]["verified"] is True
    assert by_code["371175"]["error"] == ""
    assert by_code["111111"]["status"] == "skipped"
    assert by_code["111111"]["error_code"] == "IPO_BLACKLISTED"
    assert by_code["222222"]["status"] == "skipped"
    assert user.submit_calls == 1
    assert clicks["deselect"] == [1, 2]


def test_permissions_are_not_batch_filter(monkeypatch, tmp_path):
    clicks = _patch_ui(monkeypatch)
    monkeypatch.setattr(ipo, "read_ipo_grid", lambda _user: [_grid()[0]])
    user = _User(rows=[{"证券代码": "371175", "证券名称": "中科转债"}])
    results = ipo.batch_subscribe(
        user,
        ledger=OrderLedger("2026-10-19", root=tmp_path),
        account_id="甲",
        allowlist=[{"name": "中科转债", "apply_code": "371175", "permissions": []}],
        blacklist=[],
    )
    assert results[0]["status"] == "submitted"
    assert ipo.SUBMIT_CTRL in clicks["buttons"]


def test_unknown_grid_row_rejects_whole_batch(monkeypatch, tmp_path):
    clicks = _patch_ui(monkeypatch)
    monkeypatch.setattr(ipo, "read_ipo_grid", lambda _user: _grid() + [
        {"新股名称": "未知", "新股代码": "999999", "申购数量": "1000"}
    ])
    user = _User(rows=[])
    results = ipo.batch_subscribe(
        user,
        ledger=OrderLedger("2026-10-19", root=tmp_path),
        account_id="甲",
        allowlist=_allowlist(),
        blacklist=[],
    )
    assert [r["status"] for r in results] == ["batch_rejected"] * 4
    assert results[-1]["error_code"] == "IPO_GRID_UNKNOWN_ROW"
    assert user.submit_calls == 0
    assert clicks["buttons"] == []


def test_missing_or_ambiguous_allowlist_rejects_whole_batch(monkeypatch, tmp_path):
    _patch_ui(monkeypatch)
    user = _User(rows=[])
    for allowlist in ([], [
        {"name": "中科转债", "apply_code": "371175"},
        {"name": "同代码异名", "apply_code": "371175"},
    ]):
        results = ipo.batch_subscribe(
            user,
            ledger=OrderLedger("2026-10-19", root=tmp_path),
            account_id="甲",
            allowlist=allowlist,
            blacklist=[],
        )
        assert all(r["status"] == "batch_rejected" for r in results)
        assert all(r["error"] for r in results)
    assert user.submit_calls == 0


def test_f8_query_failure_is_unverified_with_error_fields(monkeypatch, tmp_path):
    _patch_ui(monkeypatch)
    user = _User(query_error=RuntimeError("F8 查询失败 account=326219248611"))
    results = ipo.batch_subscribe(
        user,
        ledger=OrderLedger("2026-10-19", root=tmp_path),
        account_id="丙",
        allowlist=_allowlist(),
        blacklist=["111111"],
    )
    assert results[0]["status"] == "submitted_unverified"
    assert results[0]["verified"] is None
    assert results[0]["error_code"] == "IPO_ENTRUST_UNVERIFIED"
    assert "326219248611" in results[0]["error"]  # 去脱敏：账号完整保留


def test_dry_run_reads_batch_grid_without_submit(monkeypatch):
    clicks = _patch_ui(monkeypatch)
    user = _User()
    results = ipo.batch_subscribe(
        user,
        allowlist=_allowlist(),
        blacklist=["111111"],
        dry_run=True,
    )
    assert [r["status"] for r in results] == ["dry_run", "skipped", "skipped"]
    assert user.submit_calls == 0
    assert clicks["buttons"] == []


