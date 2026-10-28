# AI-SUMMARY: 同花顺自绘用户名 OCR——64位 RapidOCR 识别后仅返回已知用户名的唯一模糊匹配
from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Mapping, Sequence

_OCR_ENGINE = None


def _normalized(value: object) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def match_username(
    texts: Sequence[str],
    usernames: Sequence[str],
    *,
    min_score: float = 0.78,
    min_margin: float = 0.12,
) -> dict:
    """只在配置已知 username 中唯一匹配；不返回 OCR 原文。"""
    candidates = list(dict.fromkeys(str(value).strip() for value in usernames if str(value).strip()))
    if not candidates:
        return {"status": "unmatched", "reason": "no_known_username"}
    values = [str(value or "") for value in texts if str(value or "").strip()]
    joined = " ".join(values)
    scored = []
    for username in candidates:
        target = _normalized(username)
        score = 0.0
        for text in values + [joined]:
            value = _normalized(text)
            if not value:
                continue
            if target and target in value:
                score = max(score, 1.0)
            elif value and value in target and len(value) >= 6:
                score = max(score, SequenceMatcher(None, value, target).ratio())
            else:
                score = max(score, SequenceMatcher(None, value, target).ratio())
        scored.append((score, username))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored or scored[0][0] < float(min_score):
        return {"status": "unmatched", "reason": "score_below_threshold"}
    if len(scored) > 1 and scored[0][0] - scored[1][0] < float(min_margin):
        return {
            "status": "ambiguous",
            "reason": "margin_below_threshold",
            "score": round(scored[0][0], 4),
            "margin": round(scored[0][0] - scored[1][0], 4),
        }
    return {
        "status": "matched",
        "username": scored[0][1],
        "score": round(scored[0][0], 4),
        "margin": round(scored[0][0] - scored[1][0], 4) if len(scored) > 1 else 1.0,
    }


def cluster_ocr_row_items(items: Sequence[Mapping[str, object]]) -> list[dict]:
    """按 OCR 垂直坐标合并同一行文本和边界；只用于菜单行解析，不写日志。"""
    ordered = sorted(
        (
            {
                "text": str(item.get("text") or "").strip(),
                "left": float(item.get("left") or 0),
                "top": float(item.get("top") or 0),
                "bottom": float(item.get("bottom") or 0),
                "right": float(item.get("right") or 0),
            }
            for item in items
            if str(item.get("text") or "").strip()
        ),
        key=lambda item: (item["top"], item["left"]),
    )
    rows: list[dict] = []
    for item in ordered:
        if rows and item["top"] <= rows[-1]["bottom"] + 1:
            rows[-1]["items"].append(item)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], item["bottom"])
            continue
        rows.append({"items": [item], "top": item["top"], "bottom": item["bottom"]})
    return [
        {
            "text": " ".join(part["text"] for part in sorted(row["items"], key=lambda x: x["left"])),
            "left": min(part["left"] for part in row["items"]),
            "top": row["top"],
            "right": max(part.get("right", part["left"]) for part in row["items"]),
            "bottom": row["bottom"],
        }
        for row in rows
    ]


def cluster_ocr_rows(items: Sequence[Mapping[str, object]]) -> list[str]:
    return [str(row["text"]) for row in cluster_ocr_row_items(items)]


def _chromatic_text_image(image):
    """分离彩色自绘文字（如紫色/红色用户名）为黑字白底并放大；无彩色像素时返回 None。"""
    import numpy as np
    from PIL import Image

    arr = np.array(image.convert("RGB")).astype(int)
    peak = arr.max(axis=2)
    floor = arr.min(axis=2)
    mask = (peak - floor > 40) & (floor < 200)
    if int(mask.sum()) < 10:
        return None
    out = np.full_like(arr, 255)
    out[mask] = [0, 0, 0]
    variant = Image.fromarray(out.astype("uint8"))
    return variant.resize((variant.width * 4, variant.height * 4), Image.LANCZOS)


def _rapid_ocr():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _run_ocr_texts(image) -> list[str]:
    result, _ = _rapid_ocr()(image)
    return [str(row[1]).strip() for row in (result or []) if len(row) >= 2 and str(row[1]).strip()]


def match_image_username(image, usernames, *, min_score: float = 0.78, min_margin: float = 0.12) -> dict:
    """先直接 OCR；不匹配时分离彩色自绘文字放大后重试一次。"""
    result = match_username(_run_ocr_texts(image), usernames, min_score=min_score, min_margin=min_margin)
    if result.get("status") == "matched":
        return result
    variant = _chromatic_text_image(image)
    if variant is None:
        return result
    retry = match_username(_run_ocr_texts(variant), usernames, min_score=min_score, min_margin=min_margin)
    return retry if retry.get("status") == "matched" else result


def _ocr_items(image_path: Path) -> list[dict]:
    from PIL import Image

    image = Image.open(image_path)
    result, _ = _rapid_ocr()(image)
    items = []
    for row in result or []:
        if len(row) < 2 or not str(row[1]).strip():
            continue
        points = row[0]
        items.append({
            "text": str(row[1]).strip(),
            "left": min(float(point[0]) for point in points),
            "top": min(float(point[1]) for point in points),
            "right": max(float(point[0]) for point in points),
            "bottom": max(float(point[1]) for point in points),
        })
    return items


def _ocr_texts(image_path: Path) -> list[str]:
    return [item["text"] for item in _ocr_items(image_path)]


def _norm_header(value: str) -> str:
    return "".join(str(value or "").split())


def _cluster_items_with_cells(items: Sequence[Mapping[str, object]]) -> list[dict]:
    """按 y 聚类 OCR 条目并保留单元格明细（cluster_ocr_row_items 的投影会丢弃 items）。"""
    ordered = sorted(
        (
            {
                "text": str(item.get("text") or "").strip(),
                "left": float(item.get("left") or 0),
                "top": float(item.get("top") or 0),
                "bottom": float(item.get("bottom") or 0),
                "right": float(item.get("right") or 0),
            }
            for item in items
            if str(item.get("text") or "").strip()
        ),
        key=lambda item: (item["top"], item["left"]),
    )
    rows: list[dict] = []
    for item in ordered:
        if rows and item["top"] <= rows[-1]["bottom"] + 1:
            rows[-1]["items"].append(item)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], item["bottom"])
            continue
        rows.append({"items": [item], "top": item["top"], "bottom": item["bottom"]})
    return rows


def grid_rows_from_items(items: Sequence[Mapping[str, object]],
                         header_keys: Sequence[str] | None = None) -> list[dict] | None:
    """OCR 条目按表头 x 坐标映射列、按 y 聚类行；无表头返回 None（读取失败），有表头无数据返回 []。"""
    rows = _cluster_items_with_cells(items)
    if not rows:
        return []
    header = None
    for row in rows:
        cells = [part for part in row.get("items", [])]
        texts = [_norm_header(part["text"]) for part in sorted(cells, key=lambda x: x["left"])]
        known = [t for t in texts if t]
        if header_keys is not None and not any(k in known for k in header_keys):
            continue
        if len(known) >= 2:
            header = [(part["text"], float(part["left"])) for part in sorted(cells, key=lambda x: x["left"])]
            header_top = float(row["top"])
            break
    if header is None:
        return None
    out = []
    for row in rows:
        if float(row["top"]) <= header_top:
            continue
        record: dict[str, object] = {}
        for part in row.get("items", []):
            text = str(part.get("text") or "").strip()
            if not text:
                continue
            left = float(part["left"])
            name = min(header, key=lambda h: abs(h[1] - left))[0]
            record[name] = (str(record.get(name, "")) + " " + text).strip()
        if record:
            record["_top"] = float(row["top"])
            record["_bottom"] = float(row["bottom"])
            out.append(record)
    return out


def _resolve_ocr_python() -> list[str]:
    """64 位 OCR helper 解释器：环境变量 > 项目 .venv-test > py -3.12 > 当前解释器。"""
    import os
    import shutil

    configured = os.environ.get("AUTO_IPO_OCR_PYTHON")
    if configured:
        return [configured]
    helper = Path(sys.executable).parent.parent / ".venv-test" / "Scripts" / "python.exe"
    if helper.is_file():
        return [str(helper)]
    py = shutil.which("py")
    if py:
        return [py, "-3.12"]
    return [sys.executable]


class _OcrWorker:
    """常驻 64 位 OCR 子进程（JSON 行协议），避免每次调用冷启动 RapidOCR。"""

    def __init__(self, popen_fn=None) -> None:
        import subprocess

        self._popen_fn = popen_fn or subprocess.Popen
        self._proc = None
        self._queue = None
        self._reader = None

    def _spawn(self) -> None:
        import queue
        import threading

        command = _resolve_ocr_python() + [str(Path(__file__).resolve()), "--serve"]
        self._proc = self._popen_fn(
            command,
            stdin=__import__("subprocess").PIPE,
            stdout=__import__("subprocess").PIPE,
            stderr=__import__("subprocess").DEVNULL,
            text=True,
            encoding="utf-8",
        )
        self._queue = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        try:
            for line in self._proc.stdout:
                self._queue.put(line)
        except Exception:
            pass

    def request(self, image_path, mode: str, payload=None, *, timeout_s: float = 30.0):
        """成功返回结果 dict；worker 不可用/协议错误返回 None（调用方回退一次性子进程）。"""
        try:
            if self._proc is None or self._proc.poll() is not None:
                self.close()
                self._spawn()
            line = json.dumps(
                {"image": str(image_path), "mode": mode, "payload": dict(payload or {})},
                ensure_ascii=True,
            )
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            answer = self._queue.get(timeout=max(1.0, float(timeout_s)))
            result = json.loads(answer)
            if not isinstance(result, dict) or result.get("status") == "error":
                raise RuntimeError("ocr worker error")
            return result
        except Exception:
            self.close()
            return None

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            pass


_WORKER = None


def _worker() -> _OcrWorker:
    global _WORKER
    if _WORKER is None:
        import atexit

        _WORKER = _OcrWorker()
        atexit.register(_WORKER.close)
    return _WORKER


def serve_request(image_path, mode: str, payload=None, *, timeout_s: float = 30.0):
    """常驻 OCR worker 请求；仅 32 位进程需要，64 位/失败返回 None 走原有一次性子进程。"""
    import struct

    if struct.calcsize("P") * 8 == 64:
        return None
    return _worker().request(image_path, mode, payload, timeout_s=timeout_s)


def _process(image_path: Path, mode: str, payload: Mapping) -> dict:
    """64 位侧统一处理 match/menu/grid/raw 四种模式。"""
    if mode == "menu":
        rows = cluster_ocr_row_items(_ocr_items(image_path))
        return {"status": "ok", "rows": [row["text"] for row in rows], "items": rows}
    if mode == "raw":
        return {"status": "ok", "texts": _ocr_texts(image_path), "items": _ocr_items(image_path)}
    if mode == "grid":
        rows = grid_rows_from_items(_ocr_items(image_path))
        return {"status": "ok", "found_header": rows is not None, "rows": rows or []}
    from PIL import Image

    return match_image_username(
        Image.open(image_path),
        payload.get("usernames") or [],
        min_score=float(payload.get("min_score", 0.78)),
        min_margin=float(payload.get("min_margin", 0.12)),
    )


def _serve_loop(stdin, stdout) -> int:
    """常驻服务模式：逐行读 {"image","mode","payload"}，逐行写结果。"""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            image_path = Path(str(req.get("image") or ""))
            if not image_path.is_file():
                raise FileNotFoundError("image missing")
            result = _process(image_path, str(req.get("mode") or "match"), req.get("payload") or {})
        except Exception:
            result = {"status": "error", "reason": "ocr_failed"}
        stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
        stdout.flush()
    return 0


def read_menu_rows_with_ocr(image_path: Path, *, with_positions: bool = False) -> list:
    """32 位调用 64 位 helper 读取菜单行；原始文本只返回给调用方内存解析。"""
    import shutil
    import struct
    import subprocess
    import sys

    served = serve_request(image_path, "menu", timeout_s=20)
    if served is not None:
        if served.get("status") != "ok":
            raise RuntimeError("OCR_MENU_FAILED")
        if with_positions:
            return [dict(value) for value in served.get("items") or []]
        return [str(value) for value in served.get("rows") or []]
    if struct.calcsize("P") * 8 == 64:
        return None
    helper = Path(sys.executable).parent.parent / ".venv-test" / "Scripts" / "python.exe"
    configured = __import__("os").environ.get("AUTO_IPO_OCR_PYTHON")
    if configured:
        command = [configured]
    elif helper.is_file():
        command = [str(helper)]
    else:
        py = shutil.which("py")
        command = [py, "-3.12"] if py else [sys.executable]
    command += [str(Path(__file__).resolve()), "--image", str(image_path), "--mode", "menu"]
    if command is None:
        rows = cluster_ocr_row_items(_ocr_items(image_path))
        return [dict(row) for row in rows] if with_positions else [str(row["text"]) for row in rows]
    proc = subprocess.run(command, text=True, capture_output=True, timeout=20, input="{}")
    result = json.loads(proc.stdout or "{}")
    if proc.returncode != 0 or result.get("status") != "ok":
        raise RuntimeError("OCR_MENU_FAILED")
    if with_positions:
        return [dict(value) for value in result.get("items") or []]
    return [str(value) for value in result.get("rows") or []]


def read_grid_with_ocr(image_path: Path, *, header_keys=None) -> list[dict] | None:
    """32 位调用 64 位 helper 读网格；None=未读到表头（读取失败）。"""
    import shutil
    import subprocess
    import sys

    served = serve_request(image_path, "grid", timeout_s=30)
    if served is not None:
        if served.get("status") != "ok":
            raise RuntimeError("OCR_GRID_FAILED")
        return served["rows"] if served.get("found_header") else None

    py = shutil.which("py")
    command = [py, "-3.12"] if py else [sys.executable]
    command += [str(Path(__file__).resolve()), "--image", str(image_path), "--mode", "grid"]
    if command is None:
        return grid_rows_from_items(_ocr_items(image_path), header_keys=header_keys)
    proc = subprocess.run(command, text=True, capture_output=True, timeout=30, input="{}")
    result = json.loads(proc.stdout or "{}")
    if proc.returncode != 0 or result.get("status") != "ok":
        raise RuntimeError("OCR_GRID_FAILED")
    return result["rows"] if result.get("found_header") else None


def read_texts_with_ocr(image_path: Path) -> list[dict]:
    """32 位调用 64 位 helper 返回带坐标的原始 OCR 条目。"""
    import shutil
    import subprocess
    import sys

    served = serve_request(image_path, "raw", timeout_s=30)
    if served is not None:
        if served.get("status") != "ok":
            raise RuntimeError("OCR_RAW_FAILED")
        return [dict(item) for item in served.get("items") or []]

    py = shutil.which("py")
    command = [py, "-3.12"] if py else [sys.executable]
    command += [str(Path(__file__).resolve()), "--image", str(image_path), "--mode", "raw"]
    if command is None:
        return [dict(item) for item in _ocr_items(image_path)]
    proc = subprocess.run(command, text=True, capture_output=True, timeout=30, input="{}")
    result = json.loads(proc.stdout or "{}")
    if proc.returncode != 0 or result.get("status") != "ok":
        raise RuntimeError("OCR_RAW_FAILED")
    return [dict(item) for item in result.get("items") or []]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image")
    parser.add_argument("--mode", choices=["match", "menu", "grid", "raw"], default="match")
    parser.add_argument("--serve", action="store_true", help="常驻模式：stdin/stdout JSON 行协议")
    args = parser.parse_args()
    if args.serve:
        try:
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        return _serve_loop(sys.stdin, sys.stdout)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        image_path = Path(args.image)
        if not image_path.is_file():
            raise FileNotFoundError("image missing")
        result = _process(image_path, args.mode, payload)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception:
        print(json.dumps({"status": "error", "reason": "ocr_failed"}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
