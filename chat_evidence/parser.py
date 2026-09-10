"""把 OCR 文本行还原为带说话人和时间戳的消息序列。

三条硬规则（对应证据规则要求）：
1. 识别不出的一律留空并标记，绝不补全、不臆测；
2. 说话人通过气泡在屏幕上的左右位置判定，右侧默认为持机人（我方）；
3. 微信只在消息间隔较大时才插入时间戳，因此大量消息需沿用前一时间戳，
   报告中以 "≈" 前缀标注为"沿用时间"，提示使用时注意。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from .config import (
    CENTER_BAND,
    HEADER_ZONE,
    KIND_RULES,
    MERGE_LINE_GAP_RATIO,
    SYSTEM_KEYWORDS,
)
from .models import Message, RawLine

DATE_RE = re.compile(
    r"(20\d{2})\s*[年\-/\.]\s*(\d{1,2})\s*[月\-/\.]\s*(\d{1,2})\s*日?"
)
TIME_RE = re.compile(r"(上午|下午|早上|晚上)?\s*(\d{1,2})\s*[:：]\s*(\d{2})")
RELATIVE_DAYS = {"前天": -2, "昨天": -1, "今天": 0, "明天": 1}
WEEKDAYS = {"星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4,
            "星期六": 5, "星期日": 6, "周一": 0, "周二": 1, "周三": 2, "周四": 3,
            "周五": 4, "周六": 5, "周日": 6}


def parse_datetime(text: str, base: Optional[datetime] = None) -> Tuple[Optional[datetime], bool]:
    """解析时间文本。返回 (datetime, 是否含绝对日期)。

    支持：2025年8月31日 01:59 / 2025-08-31 01:59 / 昨天 10:06 /
         星期三 10:06 / 上午10:20 / 10:06
    """
    if not text:
        return None, False

    date_part = None
    m = DATE_RE.search(text)
    if m:
        try:
            date_part = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            date_part = None

    hm = TIME_RE.search(text)
    hour = minute = 0
    if hm:
        hour = int(hm.group(2))
        meridiem = hm.group(1)
        if meridiem in ("下午", "晚上") and hour < 12:
            hour += 12
        elif meridiem in ("上午", "早上") and hour == 12:
            hour = 0
        minute = int(hm.group(3))

    if date_part:
        return date_part.replace(hour=hour, minute=minute, second=0, microsecond=0), True

    # 无绝对日期：相对日期 / 星期，需要参照日
    ref = base
    delta = None
    for word, d in RELATIVE_DAYS.items():
        if word in text:
            delta = d
            break
    if delta is None:
        for word, wd in WEEKDAYS.items():
            if word in text:
                if ref:
                    delta = (wd - ref.weekday()) % 7
                    if delta == 0:
                        delta = 0
                break
    if ref is None:
        return None, False
    if delta is None and hm:
        delta = 0  # 仅时间：视为参照日当天
    if delta is None:
        return None, False
    return (ref + timedelta(days=delta)).replace(hour=hour, minute=minute,
                                                  second=0, microsecond=0), False


def detect_kind(text: str) -> str:
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in text:
                return kind
    return "文本"


def is_meta_line(text: str, line: RawLine) -> bool:
    """判断是否为居中元信息行（日期分隔、时间戳、系统提示）。

    重要：只有"能解析出日期/时间"或"命中系统提示关键词"的行才判为元信息。
    绝不能因为"文本居中且较短"就丢弃——短气泡同样可能居中，
    静默丢弃证据是比识别错误更严重的问题。
    """
    t = text.strip()
    if not t:
        return True
    for k in SYSTEM_KEYWORDS:
        if k in t:
            return True
    if abs(line.cx - 0.5) < CENTER_BAND and (DATE_RE.search(t) or TIME_RE.search(t)):
        return True
    return False


def speaker_of(line: RawLine, right_is_me: bool = True) -> str:
    """按气泡贴边方向判定说话人。右侧默认为持机人（我方）。"""
    dist_right = 1.0 - line.x1
    dist_left = line.x0
    if abs(dist_right - dist_left) < 0.02:
        right_side = line.cx > 0.5
    else:
        right_side = dist_right < dist_left
    me = right_side if right_is_me else not right_side
    return "我方" if me else "对方"


def build_messages(lines: List[RawLine], right_is_me: bool = True) -> List[Message]:
    """将文本行序列组装为消息序列。"""
    ordered = sorted(lines, key=lambda l: (l.page, l.y0))
    messages: List[Message] = []
    current_dt: Optional[datetime] = None      # 最近一次绝对日期
    stamp_dt: Optional[datetime] = None        # 最近一次时间戳
    stamp_text: str = ""
    stamp_used: bool = False                   # 该时间戳是否已被某条消息使用
    prev_line: Optional[RawLine] = None        # 上一行文本，用于判断气泡内换行

    for line in ordered:
        text = line.text.strip()
        if not text:
            continue
        if line.y0 < HEADER_ZONE:
            continue  # 顶部导航栏（对方昵称、返回箭头等），不作为聊天内容

        if is_meta_line(text, line):
            prev_line = None
            dt, has_date = parse_datetime(text, base=current_dt or stamp_dt)
            if dt:
                if has_date:
                    current_dt = dt
                stamp_dt = dt
                stamp_text = _clean_stamp(text)
                stamp_used = False
            elif any(k in text for k in SYSTEM_KEYWORDS):
                messages.append(
                    Message(seq=len(messages) + 1, content=text, time_text=stamp_text,
                            dt=stamp_dt, speaker="系统", kind=detect_kind(text),
                            source=line.source, confidence="medium")
                )
            continue

        # 气泡内换行：短尾行往往贴着气泡左内侧，仅凭几何位置会误判说话人，
        # 因此凡是与上一行同属一个气泡（纵向间距极小）的，一律沿用上一行的说话人。
        is_wrap = bool(
            messages
            and prev_line is not None
            and prev_line.source == line.source
            and (line.y0 - prev_line.y1) < MERGE_LINE_GAP_RATIO * max(line.height, 0.01)
        )

        speaker = messages[-1].speaker if is_wrap else speaker_of(line, right_is_me)
        kind = detect_kind(text)

        if any(k in text for k in SYSTEM_KEYWORDS):
            speaker = "系统"

        use_dt = stamp_dt or current_dt
        if stamp_dt is not None and not stamp_used:
            time_text, confidence = stamp_text, "high"
            stamp_used = True
        elif use_dt is not None:
            time_text, confidence = f"≈{stamp_text or _fmt(current_dt)}", "inherit"
        else:
            time_text, confidence = "", "low"

        can_merge = bool(
            is_wrap
            and messages[-1].speaker == speaker
            and messages[-1].source == line.source
        )

        if can_merge:
            messages[-1].content += text
            if kind != "文本":
                messages[-1].kind = kind
            prev_line = line
            continue

        msg = Message(
            seq=len(messages) + 1,
            content=text,
            time_text=time_text,
            dt=use_dt,
            speaker=speaker,
            kind=kind,
            source=line.source,
            confidence=confidence,
        )
        messages.append(msg)
        prev_line = line

    _dedup_overlap(messages)
    for i, m in enumerate(messages, 1):
        m.seq = i
    return messages


def _dedup_overlap(messages: List[Message]) -> None:
    """相邻截图常有重叠区域，同一条长消息可能被识别两次，此处去重。"""
    out: List[Message] = []
    for m in messages:
        if (
            out
            and out[-1].content == m.content
            and out[-1].speaker == m.speaker
            and len(m.content) >= 8
        ):
            continue
        out.append(m)
    messages[:] = out


def _clean_stamp(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""
