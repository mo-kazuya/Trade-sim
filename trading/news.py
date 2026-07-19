"""Lightweight, offline news-sentiment scoring.

A keyword lexicon (Japanese + English) of market-moving terms is matched
against pasted headlines to produce a sentiment score in ``[-1, 1]``. That
score is then translated into a daily drift shift and a volatility multiplier
that tilt the Monte-Carlo forecast.

This is intentionally simple and dependency-free so it runs anywhere. It is
designed as a drop-in point: replace :func:`score_news` with a call to a news
API or an LLM to upgrade the analysis without touching the forecast engine.
"""

import math

# term -> weight. Positive terms push sentiment up, negative down. Weights are
# larger for strong, price-moving catalysts (buyouts, guidance cuts, ...).
POSITIVE_TERMS = {
    # Japanese
    "買収": 3.0, "TOB": 3.0, "公開買付": 3.0, "経営統合": 2.0, "業務提携": 1.5,
    "上方修正": 3.0, "増配": 2.0, "自社株買い": 2.0, "最高益": 2.5, "過去最高": 2.0,
    "黒字転換": 2.5, "好決算": 2.5, "増益": 1.5, "増収": 1.2, "受注": 1.2,
    "承認": 2.0, "認可": 2.0, "特需": 1.5, "格上げ": 2.0, "目標株価引き上げ": 2.0,
    "新製品": 1.0, "提携": 1.2, "急騰": 1.5, "ストップ高": 3.0, "好材料": 1.5,
    "上場": 1.2, "黒字": 1.2, "回復": 1.0, "成長": 1.0,
    # English
    "acquisition": 3.0, "buyout": 3.0, "takeover": 3.0, "merger": 2.0,
    "beats": 2.5, "beat estimates": 2.5, "record profit": 2.5, "upgrade": 2.0,
    "raised guidance": 3.0, "guidance raise": 3.0, "buyback": 2.0, "dividend hike": 2.0,
    "approval": 2.0, "approved": 1.8, "breakthrough": 2.0, "partnership": 1.2,
    "surge": 1.5, "soars": 1.8, "rally": 1.2, "outperform": 1.5, "strong demand": 1.5,
}

NEGATIVE_TERMS = {
    # Japanese
    "下方修正": 3.0, "減配": 2.0, "無配": 2.5, "赤字転落": 2.5, "赤字": 1.5,
    "減益": 1.5, "減収": 1.2, "業績悪化": 2.0, "リコール": 2.0, "不正": 2.5,
    "粉飾": 3.0, "訴訟": 1.5, "破綻": 3.5, "倒産": 3.5, "上場廃止": 3.5,
    "格下げ": 2.0, "目標株価引き下げ": 2.0, "急落": 1.5, "ストップ安": 3.0,
    "悪材料": 1.5, "リストラ": 1.2, "延期": 1.2, "撤退": 1.5, "希薄化": 1.5,
    "増資": 1.5, "行政処分": 2.0, "調査": 1.0,
    # English
    "downgrade": 2.0, "misses": 2.5, "miss estimates": 2.5, "profit warning": 3.0,
    "cut guidance": 3.0, "guidance cut": 3.0, "lawsuit": 1.5, "recall": 2.0,
    "fraud": 3.0, "bankruptcy": 3.5, "delisting": 3.5, "investigation": 1.5,
    "plunge": 1.8, "tumbles": 1.8, "slump": 1.5, "underperform": 1.5, "dilution": 1.5,
    "weak demand": 1.5, "layoffs": 1.2, "default": 2.5,
}

# Tuning constants.
_SCALE = 4.0          # divides the raw weighted sum before tanh
_DRIFT_K = 0.012      # max per-day log-return shift at |sentiment| = 1
_VOL_K = 0.6          # max fractional volatility increase at |sentiment| = 1


def score_news(text):
    """Score headline ``text`` and return ``(sentiment, matched)``.

    ``sentiment`` is in ``[-1, 1]``. ``matched`` is a list of
    ``{"term", "polarity", "weight", "count"}`` for the UI.
    """
    if not text or not text.strip():
        return 0.0, []

    lowered = text.lower()
    raw = 0.0
    matched = []

    for term, weight in POSITIVE_TERMS.items():
        count = _count(text, lowered, term)
        if count:
            raw += weight * count
            matched.append(
                {"term": term, "polarity": "pos", "weight": weight, "count": count}
            )

    for term, weight in NEGATIVE_TERMS.items():
        count = _count(text, lowered, term)
        if count:
            raw -= weight * count
            matched.append(
                {"term": term, "polarity": "neg", "weight": weight, "count": count}
            )

    sentiment = math.tanh(raw / _SCALE)
    matched.sort(key=lambda m: m["weight"], reverse=True)
    return sentiment, matched


def _count(text, lowered, term):
    # ASCII terms match case-insensitively; Japanese terms match as-is.
    if term.isascii():
        return lowered.count(term.lower())
    return text.count(term)


def news_adjustments(sentiment):
    """Translate a sentiment score into ``(drift_adjust, vol_adjust)``.

    * ``drift_adjust`` shifts each day's log return (positive news -> upward).
    * ``vol_adjust`` multiplies volatility; *any* strong news (good or bad)
      raises uncertainty, widening the range of outcomes.
    """
    drift_adjust = sentiment * _DRIFT_K
    vol_adjust = 1.0 + abs(sentiment) * _VOL_K
    return drift_adjust, vol_adjust
