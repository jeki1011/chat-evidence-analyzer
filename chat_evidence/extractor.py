"""法律要件提取（规则驱动）。

重要说明：本模块只做"事实线索的定位与归类"，输出的是待复核的候选线索，
不构成法律定性。是否构成要约、承诺、违约、自认，须由执业律师结合全案判断。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .config import AMOUNT_PATTERNS, ELEMENT_RULES, REVIEW_HINTS
from .models import Message

ANY_DENY = [
    "保证不了", "不能保证", "没法保证", "没有看懂", "没说过",
    "不承认", "没办法", "还不了", "不认可", "没这回事",
]
ASK_CUE = ["保证", "承诺", "要", "必须", "得", "招", "床位", "张床", "负责"]


def extract_amounts(messages: List[Message]) -> List[Dict[str, Any]]:
    """提取金额线索。仅统计文字中明确出现的数字，不做任何换算推断。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        if m.kind not in ("转账", "文本", "文件"):
            continue
        for pat in AMOUNT_PATTERNS:
            for mm in re.finditer(pat, m.content):
                raw = mm.group(0)
                num = float(mm.group(1))
                if "万" in raw:      # 统一处理"2万""5万元""¥3万"等写法
                    num *= 10000
                out.append(
                    {
                        "seq": m.seq,
                        "时间": m.time_text or "[缺失]",
                        "说话人": m.speaker,
                        "原文": raw,
                        "数值": num,
                        "语境": m.content[:60],
                    }
                )
                break  # 一条消息每个模式只取首个，避免重复噪声
    return out


def extract_elements(messages: List[Message]) -> Dict[str, List[Dict[str, Any]]]:
    """按法律要件关键词库归类消息。"""
    findings: Dict[str, List[Dict[str, Any]]] = {k: [] for k in ELEMENT_RULES}
    for m in messages:
        if m.speaker == "系统":
            continue
        for category, rules in ELEMENT_RULES.items():
            for label, keys in rules:
                if any(k in m.content for k in keys):
                    findings[category].append(
                        {
                            "seq": m.seq,
                            "时间": m.time_text or "[缺失]",
                            "说话人": m.speaker,
                            "要点": label,
                            "内容": m.content[:120],
                        }
                    )
                    break
    return findings


def split_by_party(findings: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """把"自认"与"违约指控"拆成对我方有利 / 不利两类，避免一边倒。"""
    favorable = [x for x in findings.get("自认", []) if x["说话人"] == "对方"]
    adverse = [x for x in findings.get("违约与争议", []) if x["说话人"] == "对方"]
    our_claims = [x for x in findings.get("违约与争议", []) if x["说话人"] == "我方"]
    return {"对方不利陈述": favorable, "对我方不利陈述": adverse, "我方主张": our_claims}


def detect_contradictions(messages: List[Message]) -> List[Dict[str, Any]]:
    """逻辑矛盾候选：一方提出要求/承诺，另一方在同一话题上否认或未确认。"""
    out: List[Dict[str, Any]] = []
    for i, m in enumerate(messages):
        if m.speaker != "对方" or not any(k in m.content for k in ANY_DENY):
            continue
        for prev in messages[max(0, i - 8): i]:
            if prev.speaker == "我方" and any(k in prev.content for k in ASK_CUE):
                out.append(
                    {
                        "类型": "主张未被对方确认",
                        "我方序号": prev.seq,
                        "我方内容": prev.content[:80],
                        "对方序号": m.seq,
                        "对方内容": m.content[:80],
                        "提示": "对方在文字中明确否认或未确认我方该项主张，"
                               "以此主张欺诈/违约的风险较高，须另寻书面依据。",
                    }
                )
                break
    return out


def pending_review(messages: List[Message]) -> List[Dict[str, Any]]:
    """列出无法从截图中获取实质内容的条目，提示须调取原始载体。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        if m.kind in REVIEW_HINTS:
            out.append(
                {
                    "seq": m.seq,
                    "时间": m.time_text or "[缺失]",
                    "说话人": m.speaker,
                    "类型": m.kind,
                    "内容": m.content[:60],
                    "处理建议": REVIEW_HINTS[m.kind],
                }
            )
        elif m.confidence == "low":
            out.append(
                {
                    "seq": m.seq,
                    "时间": "[缺失]",
                    "说话人": m.speaker,
                    "类型": "时间戳缺失",
                    "内容": m.content[:60],
                    "处理建议": "无法定位时间，须核对原始载体或补充截图",
                }
            )
    return out


def analyze(messages: List[Message], gap_days: float) -> Dict[str, Any]:
    """汇总所有提取结果。"""
    findings = extract_elements(messages)
    return {
        "款项明细": extract_amounts(messages),
        "要件归类": findings,
        "立场拆分": split_by_party(findings),
        "逻辑矛盾候选": detect_contradictions(messages),
        "待复核项": pending_review(messages),
    }
