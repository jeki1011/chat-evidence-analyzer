"""命令行入口。

    python -m chat_evidence report --images ./imgs --out report.md
    python -m chat_evidence report --transcript transcript.json --out report.md
    python -m chat_evidence ocr --images ./imgs --out lines.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from .extractor import analyze
from .models import AnalysisResult
from .ocr import load_transcript, scan_directory
from .parser import build_messages
from .reporter import render
from .timeline import build_timeline, time_span


def _cmd_report(args: argparse.Namespace) -> int:
    right_is_me = not args.reverse
    if args.images:
        print(f"开始识别截图目录：{args.images}")
        lines = scan_directory(Path(args.images))
        if not lines:
            print("未识别到任何文本，请检查图片是否清晰。", file=sys.stderr)
            return 2
        messages = build_messages(lines, right_is_me=right_is_me)
        source = args.images
        image_count = len({l.source for l in lines})
    elif args.transcript:
        messages = load_transcript(Path(args.transcript))
        source = args.transcript
        image_count = 0
        print(f"已载入转录文本：{len(messages)} 条")
    else:
        print("需要指定 --images 或 --transcript", file=sys.stderr)
        return 2

    gaps = build_timeline(messages, args.gap_days)
    findings = analyze(messages, args.gap_days)
    result = AnalysisResult(
        messages=messages,
        gaps=gaps,
        findings=findings,
        meta={
            "source": source,
            "image_count": image_count,
            "span": time_span(messages),
            "owner_side": "对方" if args.reverse else "我方",
            "gap_days": args.gap_days,
        },
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(result, args.gap_days), encoding="utf-8")
    print(f"报告已生成：{out}（消息 {len(messages)} 条，时间断层 {len(gaps)} 处）")

    if args.json_out:
        jp = Path(args.json_out)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(
            json.dumps(
                {
                    "meta": result.meta,
                    "messages": [m.as_dict() for m in messages],
                    "gaps": [g.__dict__ for g in gaps],
                    "findings": findings,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"结构化数据已导出：{jp}")
    return 0


def _cmd_ocr(args: argparse.Namespace) -> int:
    lines = scan_directory(Path(args.images))
    payload = [
        {
            "text": l.text,
            "x0": round(l.x0, 4),
            "x1": round(l.x1, 4),
            "y0": round(l.y0, 4),
            "y1": round(l.y1, 4),
            "page": l.page,
            "source": l.source,
        }
        for l in lines
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"OCR 完成：{len(payload)} 行，已导出 {out}")
    return 0


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="chat-evidence",
        description="聊天记录证据分析器：截图 OCR → 时间线还原 → 法律要件提取 → 质证风险报告",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("report", help="生成证据分析报告")
    p1.add_argument("--images", help="聊天截图目录（按文件名自然排序）")
    p1.add_argument("--transcript", help="人工转录文件（.json 或 .txt），无 OCR 时使用")
    p1.add_argument("--out", required=True, help="输出 Markdown 报告路径")
    p1.add_argument("--json-out", help="同时导出结构化 JSON")
    p1.add_argument("--gap-days", type=float, default=7, help="时间断层阈值（天），默认 7")
    p1.add_argument(
        "--reverse",
        action="store_true",
        help="截图取自对方手机时使用（左右反转说话人）",
    )
    p1.set_defaults(func=_cmd_report)

    p2 = sub.add_parser("ocr", help="仅执行 OCR，导出带坐标的文本行")
    p2.add_argument("--images", required=True)
    p2.add_argument("--out", required=True)
    p2.set_defaults(func=_cmd_ocr)

    args = ap.parse_args(argv)
    return int(args.func(args))
