"""Strategy registry.

Exposes ``STRATEGIES`` (key -> class) and helpers for building a strategy
instance from user-supplied parameters.
"""

from .base import Param, Strategy
from .implementations import (
    BollingerBands,
    BuyAndHold,
    MACDStrategy,
    RSIStrategy,
    SMACrossover,
)

STRATEGY_CLASSES = [
    BuyAndHold,
    SMACrossover,
    RSIStrategy,
    BollingerBands,
    MACDStrategy,
]

STRATEGIES = {cls.key: cls for cls in STRATEGY_CLASSES}


def get_strategy_class(key):
    if key not in STRATEGIES:
        raise KeyError(f"Unknown strategy: {key}")
    return STRATEGIES[key]


def build_strategy(key, params=None):
    """Instantiate a strategy by key with the given parameter dict."""
    cls = get_strategy_class(key)
    return cls(**(params or {}))


__all__ = [
    "Param",
    "Strategy",
    "STRATEGIES",
    "STRATEGY_CLASSES",
    "get_strategy_class",
    "build_strategy",
]
