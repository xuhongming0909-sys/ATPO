# AI-SUMMARY: 探针 4——华宝资金户登录弹窗结构 + 验证码图像 OCR 可行性
import json
import sys
import time

sys.path.insert(0, r"C:\Users\93724\Desktop\自动打新")

from shared.config import load_config
from execution.client_registry import ClientSpec
from execution.ths_account_config import load_ths_account_mode, read_ths_password
from execution.ths_account_runner import GentleClientLifecycle
from execution.ths_account_ui import ThsAccountUI
from execution.ths_account_switch import ThsLoginAccount, switch_ths_account

out = {}
cfg = load_config()
mode = load_ths_account_mode(cfg)
accounts = [a for a in mode.accounts if a.enabled]
client = ClientSpec(client_id="ths_account_switch", hexin_path=mode.hexin_path, xiadan_path=mode.xiadan_path)

lifecycle = GentleClientLifecycle(client, cfg)
lifecycle.start()
try:
    ui = ThsAccountUI(client, cfg, known_ths_accounts=[a.username for a in accounts])
    switch_ths_account(ThsLoginAccount(username="mx_mbqdpecj9"), client,
                       lambda: read_ths_password("mx_mbqdpecj9"), ui, 120)
    refs = ui.discover_fund_accounts()
    out["refs"] = [r.display_masked for r in refs]
    hb = next(r for r in refs if "华宝" in r.display_masked)
    # 点击华宝行触发登录弹窗（不自动关闭）
    clicked = ui._click_main_row(hb)
    out["clicked"] = clicked.get("text")
    time.sleep(2)

    # 找登录弹窗并转储结构
    import pywinauto
    from execution.ths_client import _ctrl_visible
    dialogs = []
    for w in pywinauto.Desktop(backend="win32").windows():
        try:
            pid = w.process_id()
        except Exception:
            continue
        import win32process
        from execution.hexin_login import _hexin_pids
        if pid not in _hexin_pids(client):
            continue
        text = w.window_text() or ""
        edits = [e for e in w.descendants(class_name="Edit")]
        buttons = [b for b in w.descendants(class_name="Button") if _ctrl_visible(b)]
        if edits and any("登录" in (b.window_text() or "") for b in buttons):
            info = {
                "title": text,
                "handle": w.handle,
                "rect": str(w.rectangle()),
                "edits": [{"id": e.control_id(), "rect": str(e.rectangle()), "pwd": bool(e.is_password() if hasattr(e, "is_password") else False)} for e in edits],
                "buttons": [{"id": b.control_id(), "text": b.window_text()} for b in buttons],
                "statics": [{"id": s.control_id(), "text": (s.window_text() or "")[:20], "rect": str(s.rectangle())}
                            for s in w.descendants(class_name="Static") if _ctrl_visible(s)][:15],
            }
            dialogs.append(info)
    out["dialogs"] = dialogs
    if dialogs:
        # 截弹窗图做证据
        from PIL import ImageGrab
        dlg_rect = dialogs[0]["rect"]
        import re as _re
        nums = [int(v) for v in _re.findall(r"-?\d+", dlg_rect)]
        path = r"C:\Users\93724\Desktop\自动打新\runtime_data\debug\captcha_dialog.png"
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ImageGrab.grab(bbox=(nums[0], nums[1], nums[2], nums[3])).save(path)
        out["screenshot"] = path
finally:
    lifecycle.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
