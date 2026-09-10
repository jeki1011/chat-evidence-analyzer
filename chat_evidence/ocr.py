"""OCR 引擎适配层。

支持两种输入：
1. 图片目录 -> 调用本地 RapidOCR（纯 onnxruntime，离线可用）
2. 人工转录文本（JSON / TXT）-> 直接进入解析环节，供 OCR 不可用或需人工校订时使用

设计原则：OCR 只负责"把像素变成带坐标的文本行"，不做任何法律判断，
也不对识别结果做补全或臆测；识别不出的内容一律留空并标记待复核。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import Message, RawLine

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class OCREngine:
    """RapidOCR 封装。首次调用会加载内置模型（约 14MB，随包安装）。"""

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except ImportError as exc:  # pragma: no cover - 环境相关
            raise RuntimeError(
                "未安装 OCR 引擎。请先执行：pip install -r requirements.txt\n"
                "或改用 --transcript 模式直接输入人工转录文本。"
            ) from exc
        self._engine = RapidOCR()

    def scan_image(self, path: Path) -> List[RawLine]:
        from PIL import Image  # noqa: F401  确保 pillow 可用

        result, _ = self._engine(str(path))
        img = Image.open(path)
        w, h = img.size
        lines: List[RawLine] = []
        if not result:
            return lines
        for box, text, score in result:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(
                RawLine(
                    text=str(text).strip(),
                    x0=max(min(xs) / w, 0.0),
                    x1=min(max(xs) / w, 1.0),
                    y0=max(min(ys) / h, 0.0),
                    y1=min(max(ys) / h, 1.0),
                    page=0,
                    source=path.name,
                )
            )
        return lines


def scan_directory(images_dir: Path, progress: bool = True) -> List[RawLine]:
    """扫描目录下的所有截图（按文件名自然排序），返回全部文本行。"""
    engine = OCREngine()
    files = sorted(
        [p for p in Path(images_dir).iterdir() if p.suffix.lower() in IMAGE_EXTS],
        key=_natural_key,
    )
    if not files:
        raise FileNotFoundError(f"目录中没有找到图片：{images_dir}")

    all_lines: List[RawLine] = []
    for idx, f in enumerate(files, 1):
        if progress:
            print(f"  [{idx}/{len(files)}] 识别 {f.name}")
        for line in engine.scan_image(f):
            line.page = idx
            all_lines.append(line)
    return all_lines


def _natural_key(p: Path):
    """文件名自然排序：1.jpg < 2.jpg < 10.jpg。"""
    import re

    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


# ---------------- 转录文本模式 ----------------

def load_transcript(path: Path) -> List[Message]:
    """读取人工转录文件。

    JSON 格式（推荐）：
      [{"date":"2025-08-31","time":"01:59","speaker":"我方","content":"...","kind":"转账"}, ...]
    TXT 格式（简易）：每行一条
      2025-08-31 01:59 我方 | 先转2万诚意金
    """
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        msgs: List[Message] = []
        for i, item in enumerate(data, 1):
            dt_text = " ".join(
                x for x in [str(item.get("date", "")), str(item.get("time", ""))] if x
            ).strip()
            msgs.append(
                Message(
                    seq=i,
                    content=str(item.get("content", "")).strip(),
                    time_text=dt_text,
                    dt=_parse_dt(dt_text),
                    speaker=str(item.get("speaker", "未知")),
                    kind=str(item.get("kind", "文本")),
                    source=str(item.get("source", p.name)),
                )
            )
        return msgs

    msgs = []
    for i, raw in enumerate(
        [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()], 1
    ):
        date, time_, speaker, content = "", "", "未知", raw
        try:
            head, content = raw.split("|", 1)
            parts = head.split()
            if len(parts) >= 3:
                date, time_, speaker = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                date, time_ = parts[0], parts[1]
        except ValueError:
            pass
        dt_text = f"{date} {time_}".strip()
        msgs.append(
            Message(
                seq=i,
                content=content.strip(),
                time_text=dt_text,
                dt=_parse_dt(dt_text),
                speaker=speaker,
                source=p.name,
            )
        )
    return msgs


def _parse_dt(text: str):
    """复用 parser 的时间解析逻辑（延迟导入避免循环依赖）。

    parse_datetime 返回 (datetime, 是否含绝对日期)，此处只需前者。
    """
    from .parser import parse_datetime

    return parse_datetime(text)[0]
