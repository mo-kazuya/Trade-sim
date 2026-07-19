"""Base classes for trading strategies.

A strategy consumes a price DataFrame (indexed by date, with an ``open``,
``high``, ``low``, ``close``, ``volume`` columns) and produces a *target
position* series aligned to that index:

* ``1`` -> be fully invested (long) on that bar
* ``0`` -> be in cash on that bar

The backtest engine reads the transitions between target positions to decide
when to buy and sell.
"""

from dataclasses import dataclass


@dataclass
class Param:
    """A single tunable parameter, used to build web forms and validate input."""

    name: str
    label: str
    default: float
    kind: str = "int"  # "int" or "float"
    min: float = 0
    max: float = 10_000
    help: str = ""

    def coerce(self, value):
        if value is None or value == "":
            return self.default
        return int(value) if self.kind == "int" else float(value)


class Strategy:
    """Base strategy. Subclasses set ``key``/``label`` and implement signals."""

    key = ""
    label = ""
    description = ""
    params: list[Param] = []

    def __init__(self, **kwargs):
        # Coerce and store parameter values, falling back to defaults.
        self.values = {}
        for p in self.params:
            self.values[p.name] = p.coerce(kwargs.get(p.name))

    def __getattr__(self, item):
        # Allow ``self.<param_name>`` access to configured values.
        values = self.__dict__.get("values", {})
        if item in values:
            return values[item]
        raise AttributeError(item)

    def generate_positions(self, df):
        """Return a pandas Series of target positions (0/1) aligned to ``df``."""
        raise NotImplementedError

    @classmethod
    def param_defaults(cls):
        return {p.name: p.default for p in cls.params}
