"""单元测试（stdlib unittest，无需额外依赖）。

运行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_evidence.extractor import analyze, extract_amounts  # noqa: E402
from chat_evidence.models import Message, RawLine  # noqa: E402
from chat_evidence.parser import build_messages, detect_kind, parse_datetime  # noqa: E402
from chat_evidence.reporter import render  # noqa: E402
from chat_evidence.timeline import build_timeline  # noqa: E402


def line(text, x0, x1, y0, y1, source="1.jpg", page=1) -> RawLine:
    return RawLine(text=text, x0=x0, x1=x1, y0=y0, y1=y1, page=page, source=source)


class TestTimeParsing(unittest.TestCase):
    def test_absolute_datetime(self):
        dt, has_date = parse_datetime("2025年8月31日 01:59")
        self.assertEqual(dt, datetime(2025, 8, 31, 1, 59))
        self.assertTrue(has_date)

    def test_dash_format(self):
        dt, _ = parse_datetime("2025-08-31 10:06")
        self.assertEqual(dt, datetime(2025, 8, 31, 10, 6))

    def test_relative_day(self):
        dt, has_date = parse_datetime("昨天 10:06", base=datetime(2025, 3, 10, 9, 0))
        self.assertEqual(dt, datetime(2025, 3, 9, 10, 6))
        self.assertFalse(has_date)

    def test_meridiem(self):
        dt, _ = parse_datetime("下午2:00", base=datetime(2025, 3, 10))
        self.assertEqual(dt, datetime(2025, 3, 10, 14, 0))

    def test_empty(self):
        dt, _ = parse_datetime("")
        self.assertIsNone(dt)


class TestKindDetection(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(detect_kind("对方撤回了一条消息"), "撤回")
        self.assertEqual(detect_kind("微信转账 ¥20000"), "转账")
        self.assertEqual(detect_kind("语音 21\""), "语音")
        self.assertEqual(detect_kind("合同.pdf"), "文件")
        self.assertEqual(detect_kind("你好"), "文本")


class TestMessageBuilding(unittest.TestCase):
    def test_speaker_by_side(self):
        lines = [
            line("2025年3月10日", 0.4, 0.6, 0.20, 0.24),
            line("在吗", 0.10, 0.40, 0.30, 0.35),
            line("在的", 0.60, 0.90, 0.40, 0.45),
        ]
        msgs = build_messages(lines)
        self.assertEqual([m.speaker for m in msgs], ["对方", "我方"])
        self.assertEqual(msgs[0].time_text, "2025年3月10日")

    def test_reverse_owner(self):
        lines = [line("在的", 0.60, 0.90, 0.40, 0.45)]
        msgs = build_messages(lines, right_is_me=False)
        self.assertEqual(msgs[0].speaker, "对方")

    def test_short_bubble_not_dropped(self):
        """短气泡即便文本居中，也不能被当作时间戳丢弃。"""
        lines = [line("不行，你必须按约定还。", 0.43, 0.84, 0.40, 0.45)]
        msgs = build_messages(lines)
        self.assertEqual(len(msgs), 1)
        self.assertIn("必须", msgs[0].content)

    def test_wrap_merge(self):
        lines = [
            line("小王，三个月到了，那5万该还了", 0.29, 0.86, 0.30, 0.35),
            line("吧?", 0.29, 0.36, 0.36, 0.41),
        ]
        msgs = build_messages(lines)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "小王，三个月到了，那5万该还了吧?")
        self.assertEqual(msgs[0].speaker, "我方")

    def test_header_ignored(self):
        lines = [
            line("王强", 0.45, 0.55, 0.02, 0.05),
            line("你好", 0.60, 0.90, 0.40, 0.45),
        ]
        msgs = build_messages(lines)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "你好")


class TestTimeline(unittest.TestCase):
    def test_gap_detected(self):
        msgs = [
            Message(seq=1, content="a", time_text="2025-01-01", dt=datetime(2025, 1, 1)),
            Message(seq=2, content="b", time_text="2025-03-01", dt=datetime(2025, 3, 1)),
        ]
        gaps = build_timeline(msgs, gap_days=7)
        self.assertEqual(len(gaps), 1)
        self.assertIn("[时间断层]", gaps[0].note)

    def test_no_gap(self):
        msgs = [
            Message(seq=1, content="a", dt=datetime(2025, 1, 1)),
            Message(seq=2, content="b", dt=datetime(2025, 1, 2)),
        ]
        self.assertEqual(len(build_timeline(msgs, 7)), 0)


class TestExtraction(unittest.TestCase):
    def test_amounts(self):
        msgs = [Message(seq=1, content="已转账50000元，你查收一下。", kind="转账")]
        amounts = extract_amounts(msgs)
        self.assertEqual(len(amounts), 1)
        self.assertEqual(amounts[0]["数值"], 50000)

    def test_wan_unit(self):
        msgs = [Message(seq=1, content="先还2万")]
        self.assertEqual(extract_amounts(msgs)[0]["数值"], 20000)


class TestReport(unittest.TestCase):
    def _result(self):
        msgs = [
            Message(seq=1, content="借我5万", time_text="2025-03-10",
                    dt=datetime(2025, 3, 10), speaker="对方"),
            Message(seq=2, content="借条是我写的，钱我认", time_text="2025-03-10",
                    dt=datetime(2025, 3, 10), speaker="对方", confidence="inherit"),
            Message(seq=3, content="对方撤回了一条消息", time_text="2025-03-10",
                    dt=datetime(2025, 3, 10), speaker="系统", kind="撤回"),
        ]
        from chat_evidence.models import AnalysisResult

        gaps = build_timeline(msgs, 7)
        return AnalysisResult(
            messages=msgs,
            gaps=gaps,
            findings=analyze(msgs, 7),
            meta={"source": "test", "image_count": 1, "span": "2025-03-10", "owner_side": "我方"},
        )

    def test_report_sections(self):
        md = render(self._result(), 7)
        for sec in ["## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、"]:
            self.assertIn(sec, md)
        self.assertIn("撤回", md)
        self.assertIn("借条是我写的", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
