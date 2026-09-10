"""数据结构定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RawLine:
    """OCR 识别出的单行文本及其几何位置。

    cx / x0 / x1 均为相对图片宽度的比例（0~1），cy / y0 / y1 为相对高度比例。
    保留几何位置是为了判断气泡位于屏幕左侧还是右侧，从而区分说话人。
    """

    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    page: int
    source: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Message:
    """一条还原后的聊天消息。"""

    seq: int
    content: str = ""
    time_text: str = ""
    dt: Optional[datetime] = None
    speaker: str = "未知"          # 我方 / 对方 / 系统
    kind: str = "文本"              # 文本 / 转账 / 语音 / 图片 / 文件 / 通话 / 撤回 / 系统
    source: str = ""                # 来源截图文件名
    confidence: str = "high"        # high / medium / low（时间戳缺失等情形为 low）
    last_y: float = field(default=0.0, repr=False)  # 气泡底边纵坐标，用于换行合并

    def as_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "时间": self.time_text,
            "说话人": self.speaker,
            "类型": self.kind,
            "内容": self.content,
            "来源截图": self.source,
            "时间可信度": self.confidence,
        }


@dataclass
class Gap:
    """时间断层。"""

    after_seq: int
    from_text: str
    to_text: str
    days: float
    note: str = "[时间断层]"


@dataclass
class AnalysisResult:
    messages: List[Message] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    findings: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
