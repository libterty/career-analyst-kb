"""Career topic classifier for YouTube transcript chunks.

Assigns one or more career topic tags to a transcript chunk using keyword
matching as a fast, zero-cost first pass.  An LLM-based fallback can be
enabled for edge cases but is off by default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Topic taxonomy ────────────────────────────────────────────────────────────
# Each topic maps to a list of Chinese / English keyword patterns.
# Patterns are matched case-insensitively against chunk text.

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "resume": [
        "履歷", "resume", "CV", "作品集", "portfolio", "自我介紹", "自傳",
        "cover letter", "求職信",
    ],
    "interview": [
        "面試", "interview", "面談", "STAR", "行為面試", "behavioral",
        "case interview", "case study", "面試官", "答題",
    ],
    "job_search": [
        "找工作", "求職", "job search", "投履歷", "應徵", "獵頭", "headhunt",
        "LinkedIn", "104", "1111", "job board", "networking",
    ],
    "career_planning": [
        "職涯", "career", "規劃", "轉職", "career change", "轉行", "方向",
        "目標設定", "goal", "roadmap", "路線圖", "五年計畫", "十年計畫",
    ],
    "salary": [
        "薪水", "薪資", "salary", "待遇", "offer", "package", "談薪",
        "negotiate", "加薪", "調薪", "annual bonus", "股票", "RSU", "ESOP",
    ],
    "workplace": [
        "職場", "workplace", "同事", "主管", "上司", "老闆", "boss",
        "team", "團隊", "文化", "culture", "外商", "新創", "startup",
        "大公司", "大企業", "中小企業",
    ],
    "promotion": [
        "升遷", "晉升", "promotion", "升職", "manager", "管理", "leadership",
        "leader", "senior", "principal", "director", "VP",
    ],
    "skill_development": [
        "技能", "skill", "學習", "learn", "課程", "course", "證照",
        "certification", "upskill", "reskill", "軟技能", "soft skill",
        "溝通", "communication", "簡報", "presentation",
    ],
    "industry_insight": [
        "產業", "industry", "趨勢", "trend", "市場", "market", "AI",
        "科技", "tech", "外商", "MNC", "外資", "台積電", "TSMC",
    ],
}

FALLBACK_TOPIC = "general_career"


@dataclass(frozen=True)
class ClassificationResult:
    topics: list[str] = field(default_factory=list)
    confidence: str = "keyword"  # "keyword" | "llm" | "fallback"


def classify(text: str) -> ClassificationResult:
    """Return career topics for *text* using keyword matching.

    Returns at least one topic; falls back to FALLBACK_TOPIC when no
    keywords match.
    """
    text_lower = text.lower()
    matched: list[str] = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if re.search(re.escape(kw.lower()), text_lower):
                matched.append(topic)
                break  # one match per topic is enough

    if not matched:
        return ClassificationResult(topics=[FALLBACK_TOPIC], confidence="fallback")

    return ClassificationResult(topics=matched, confidence="keyword")
