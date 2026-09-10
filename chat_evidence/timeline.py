"""时间线处理：排序、时间断层检测、可信度标注。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .models import Gap, Message


def build_timeline(messages: List[Message], gap_days: float) -> List[Gap]:
    """检测时间断层。返回断层列表（同时会把消息按时间重排）。"""
    gaps: List[Gap] = []
    anchor: Optional[Message] = None

    for m in messages:
        if m.dt is None:
            continue
        if anchor is not None and anchor.dt is not None:
            delta = (m.dt - anchor.dt).total_seconds() / 86400.0
            if delta > gap_days:
                gaps.append(
                    Gap(
                        after_seq=anchor.seq,
                        from_text=anchor.dt.strftime("%Y-%m-%d"),
                        to_text=m.dt.strftime("%Y-%m-%d"),
                        days=round(delta, 1),
                        note=f"[时间断层] 间隔 {delta:.0f} 天无记录，须补充该时段截图",
                    )
                )
        if m.dt is not None and (anchor is None or m.dt >= (anchor.dt or m.dt)):
            anchor = m

    messages.sort(key=lambda x: (x.dt is None, x.dt or datetime.min, x.seq))
    for i, m in enumerate(messages, 1):
        m.seq = i
    return gaps


def time_span(messages: List[Message]) -> str:
    dts = [m.dt for m in messages if m.dt]
    if not dts:
        return "未知（无可用时间戳）"
    return f"{min(dts).strftime('%Y-%m-%d')} 至 {max(dts).strftime('%Y-%m-%d')}"


def low_confidence_messages(messages: List[Message]) -> List[Message]:
    return [m for m in messages if m.confidence == "low"]
