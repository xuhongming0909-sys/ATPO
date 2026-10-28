# AI-SUMMARY: 同花顺当前登录用户名 OCR 匹配测试——自绘文本模糊识别、唯一性门槛和敏感原文不回传
from execution.ths_account_ui import HexinSwitchUI
from execution.ths_account_ui import FundAccountRef
from shared.username_ocr import cluster_ocr_rows, match_username


def test_username_match_recovers_ocr_typo_without_returning_ocr_text():
    result = match_username(
        ["526378109"],
        ["mx_525378109", "mx_mbqdpecj9"],
        min_score=0.78,
        min_margin=0.12,
    )
    assert result["status"] == "matched"
    assert result["username"] == "mx_525378109"
    assert "text" not in result
    assert "ocr" not in result


def test_username_match_rejects_ambiguous_candidates():
    result = match_username(
        ["mx_abcdefgh1", "mx_abcdefgh2"],
        ["mx_abcdefgh1", "mx_abcdefgh2"],
        min_score=0.78,
        min_margin=0.12,
    )
    assert result["status"] == "ambiguous"


def test_hexin_switch_ui_uses_injected_ocr_fallback():
    class Window:
        def window_text(self):
            return "同花顺 - 自选股"

        def rectangle(self):
            return (0, 0, 1920, 1080)

    window = Window()
    ui = HexinSwitchUI(
        client=object(),
        cfg={"gui": {"ths_account_switch": {}}},
        known_ths_accounts=["mx_525378109", "mx_mbqdpecj9"],
        command_line_fn=lambda _pids: [],
        visible_texts_fn=lambda _window: [],
        username_ocr_fn=lambda _window, _known, _settings: "mx_525378109",
    )
    ui._windows = lambda visible_only=True: [window]
    assert ui.current_account_name() == "mx_525378109"


def test_ocr_menu_rows_group_texts_by_vertical_row():
    rows = cluster_ocr_rows([
        {"text": "已登录", "left": 120, "top": 10, "bottom": 20},
        {"text": "平安证券-张*龙", "left": 5, "top": 8, "bottom": 22},
        {"text": "华宝证券", "left": 5, "top": 40, "bottom": 52},
    ])
    assert rows == ["平安证券-张*龙 已登录", "华宝证券"]


def test_fund_account_ref_strips_login_status_decoration():
    first = FundAccountRef.from_label(0, "平安证券-张*龙 已登录")
    second = FundAccountRef.from_label(1, "■ 平安证券-张*龙 F12")
    assert first.key == second.key
    assert first.display_masked == second.display_masked
def test_serve_loop_processes_json_lines(tmp_path, monkeypatch):
    import io
    import json

    import shared.username_ocr as ocr

    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(ocr, "_process", lambda path, mode, payload: {"status": "ok", "mode": mode})
    stdin = io.StringIO(json.dumps({"image": str(image), "mode": "grid"}, ensure_ascii=True) + "\n")
    stdout = io.StringIO()
    assert ocr._serve_loop(stdin, stdout) == 0
    assert json.loads(stdout.getvalue().strip()) == {"status": "ok", "mode": "grid"}


def test_serve_loop_missing_image_returns_error_line():
    import io
    import json

    import shared.username_ocr as ocr

    stdin = io.StringIO(json.dumps({"image": "Z:/no/such.png", "mode": "grid"}) + "\n")
    stdout = io.StringIO()
    assert ocr._serve_loop(stdin, stdout) == 0
    assert json.loads(stdout.getvalue().strip())["status"] == "error"


def test_worker_reuses_single_process_across_requests():
    import shared.username_ocr as ocr

    spawns = []

    class FakeStdin:
        def __init__(self):
            self.lines = []

        def write(self, value):
            self.lines.append(value)

        def flush(self):
            pass

    class FakeProc:
        def __init__(self):
            self.stdin = FakeStdin()
            self._answers = ['{"status":"ok","rows":[]}', '{"status":"ok","rows":[]}']

        def poll(self):
            return None

        @property
        def stdout(self):
            return iter(self._answers)

        def kill(self):
            pass

    def fake_popen(command, **kwargs):
        spawns.append(command)
        return FakeProc()

    worker = ocr._OcrWorker(popen_fn=fake_popen)
    first = worker.request("a.png", "grid", timeout_s=5)
    second = worker.request("b.png", "raw", timeout_s=5)
    assert first == {"status": "ok", "rows": []}
    assert second == {"status": "ok", "rows": []}
    assert len(spawns) == 1
    worker.close()


def test_worker_spawn_failure_returns_none():
    import shared.username_ocr as ocr

    def bad_popen(command, **kwargs):
        raise OSError("spawn failed")

    worker = ocr._OcrWorker(popen_fn=bad_popen)
    assert worker.request("a.png", "grid", timeout_s=1) is None


def test_serve_request_skips_worker_in_64bit(monkeypatch):
    import struct

    import shared.username_ocr as ocr

    monkeypatch.setattr(struct, "calcsize", lambda _fmt: 8)
    assert ocr.serve_request("a.png", "grid") is None
