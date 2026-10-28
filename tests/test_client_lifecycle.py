# AI-SUMMARY: 客户端生命周期原语单测——find_processes 精确 exe 归属、_start 记录 PID、_close_pid 温和关闭
from pathlib import Path

from execution.client_lifecycle import _close_pid, _start, find_processes


def test_find_processes_filters_by_exact_executable(monkeypatch):
    path = Path("E:/ths/hexin.exe")
    fake = {101: "E:\\ths\\hexin.exe", 102: "E:\\ths2\\hexin.exe"}

    import subprocess

    class _R:
        stdout = '"hexin.exe","101","S","S","0","1 K"\n"hexin.exe","102","S","S","0","1 K"\n'

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    found = find_processes([path], image_path_fn=lambda pid: fake.get(pid, ""))
    assert found[str(path)] == [101]


def test_find_processes_ignores_same_name_other_dir(monkeypatch):
    path = Path("E:/ths/hexin.exe")

    import subprocess

    class _R:
        stdout = '"hexin.exe","102","S","S","0","1 K"\n'

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    found = find_processes([path], image_path_fn=lambda pid: "E:\\ths2\\hexin.exe")
    assert found[str(path)] == []


def test_start_returns_new_pid(monkeypatch, tmp_path):
    exe = tmp_path / "hexin.exe"
    exe.write_text("")

    class _P:
        pid = 555

    monkeypatch.setattr("execution.client_lifecycle.subprocess.Popen", lambda *a, **k: _P())
    monkeypatch.setattr(
        "execution.client_lifecycle.find_processes",
        lambda paths: {str(paths[0]): [555]},
    )
    pid = _start(exe, set())
    assert pid == 555


def test_close_pid_posts_wm_close_and_waits(monkeypatch):
    monkeypatch.setattr("execution.client_lifecycle._pid_active", lambda pid: True)
    monkeypatch.setattr("execution.client_lifecycle._window_pids", lambda pid: [11, 12])
    posted = []
    monkeypatch.setattr("win32gui.PostMessage", lambda hwnd, msg, w, l: posted.append(hwnd) or True)
    monkeypatch.setattr("execution.client_lifecycle._wait_exit", lambda pid, t: True)
    ok, err = _close_pid(42, 5.0)
    assert ok is True and err == ""
    assert sorted(posted) == [11, 12]


def test_close_pid_falls_back_to_taskkill_without_force(monkeypatch):
    monkeypatch.setattr("execution.client_lifecycle._pid_active", lambda pid: True)
    monkeypatch.setattr("execution.client_lifecycle._window_pids", lambda pid: [])
    calls = []
    monkeypatch.setattr(
        "execution.client_lifecycle._taskkill_close",
        lambda pid, t: calls.append(pid) or (True, ""),
    )
    monkeypatch.setattr("execution.client_lifecycle._wait_exit", lambda pid, t: len(calls) > 0)
    ok, _err = _close_pid(42, 5.0)
    assert ok is True and calls == [42]
def test_close_fails_when_scan_empty_but_tracked_pid_alive(monkeypatch):
    """核验防误报：扫描瞬断为空但已跟踪进程仍活跃时必须 close_failed，不得谎报 closed。"""
    from execution.ths_account_runner import GentleClientLifecycle

    lc = GentleClientLifecycle.__new__(GentleClientLifecycle)
    lc.client = type("C", (), {
        "hexin_path": __import__("pathlib").Path("E:/同花顺/同花顺/hexin.exe"),
        "xiadan_path": __import__("pathlib").Path("E:/同花顺/同花顺/xiadan.exe"),
    })()
    lc.cfg = {"gui": {"lifecycle": {}}}
    lc._tracked = {str(lc.client.hexin_path): {4242}}
    lc._baseline = {str(lc.client.hexin_path): set(), str(lc.client.xiadan_path): set(),
                    str(__import__("pathlib").Path("E:/同花顺/同花顺/xiadan-plus/xiadan-plus.exe")): set()}
    monkeypatch.setattr("execution.client_lifecycle.find_processes", lambda paths: {str(p): [] for p in paths})
    monkeypatch.setattr("execution.client_lifecycle._pid_active", lambda pid: True)
    monkeypatch.setattr("execution.ths_account_runner.time.sleep", lambda _s: None)
    result = lc.close()
    assert result["status"] == "close_failed"
    assert "核验异常" in result["error"]
