"""External market-data providers.

Currently supports Yahoo Finance via its public chart endpoint
(``/v8/finance/chart``), which returns OHLCV data as JSON without requiring an
API key. The network fetch and the JSON parsing are kept separate so the
parser can be unit-tested with fixtures (no network required).
"""

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]

VALID_INTERVALS = {"1d", "1wk", "1mo"}
VALID_RANGES = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"}


class DataProviderError(Exception):
    """Raised when market data cannot be fetched or parsed."""


def _build_url(host, symbol, *, range_=None, start=None, end=None, interval="1d"):
    params = {"interval": interval, "events": "div,split"}
    if start is not None and end is not None:
        params["period1"] = int(_to_timestamp(start))
        params["period2"] = int(_to_timestamp(end))
    else:
        params["range"] = range_ or "1y"
    query = urllib.parse.urlencode(params)
    symbol_q = urllib.parse.quote(symbol)
    return f"https://{host}/v8/finance/chart/{symbol_q}?{query}"


def _to_timestamp(value):
    if isinstance(value, dt.datetime):
        return value.timestamp()
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day).timestamp()
    return float(value)


def fetch_yahoo_ohlc(symbol, *, range_="1y", start=None, end=None, interval="1d",
                     timeout=25):
    """Download OHLCV bars for ``symbol`` from Yahoo Finance.

    Provide either ``range_`` (e.g. "1y", "5y", "max") or an explicit
    ``start``/``end`` (``date``/``datetime``). Returns
    ``(meta: dict, bars: list[dict])`` where each bar has date/open/high/low/
    close/volume keys.
    """
    if interval not in VALID_INTERVALS:
        raise DataProviderError(f"未対応の interval です: {interval}")

    last_error = None
    for host in YAHOO_HOSTS:
        url = _build_url(host, symbol, range_=range_, start=start, end=end,
                         interval=interval)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.load(resp)
            return parse_chart_payload(payload, fallback_symbol=symbol)
        except urllib.error.HTTPError as exc:
            # 404 means the symbol is wrong; no point trying the mirror host.
            if exc.code == 404:
                raise DataProviderError(
                    f"銘柄コード '{symbol}' が見つかりません。"
                ) from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc

    raise DataProviderError(
        f"Yahoo ファイナンスからの取得に失敗しました: {last_error}"
    )


def parse_chart_payload(payload, fallback_symbol=""):
    """Parse a Yahoo chart JSON payload into ``(meta, bars)``.

    Pure function (no network) so it can be tested with recorded fixtures.
    """
    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        desc = error.get("description") or error.get("code") or "unknown error"
        raise DataProviderError(f"Yahoo ファイナンスがエラーを返しました: {desc}")

    results = chart.get("result")
    if not results:
        raise DataProviderError("価格データが空でした。")

    result = results[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    quote = (indicators.get("quote") or [{}])[0]

    # Prefer split/dividend-adjusted closes when present.
    adjclose = None
    adj = indicators.get("adjclose")
    if adj and adj[0].get("adjclose"):
        adjclose = adj[0]["adjclose"]

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    bars = []
    for i, ts in enumerate(timestamps):
        o = _at(opens, i)
        h = _at(highs, i)
        low = _at(lows, i)
        c = _at(closes, i)
        if None in (o, h, low, c):
            # Skip incomplete rows (e.g. current in-progress bar / halts).
            continue
        bars.append(
            {
                "date": dt.datetime.utcfromtimestamp(ts).date(),
                "open": round(float(o), 4),
                "high": round(float(h), 4),
                "low": round(float(low), 4),
                "close": round(float(_at(adjclose, i, default=c)), 4),
                "volume": int(_at(volumes, i, default=0) or 0),
            }
        )

    if not bars:
        raise DataProviderError("有効な価格データがありませんでした。")

    info = {
        "symbol": meta.get("symbol") or fallback_symbol,
        "currency": meta.get("currency", ""),
        "exchange": meta.get("exchangeName", ""),
        "name": meta.get("longName") or meta.get("shortName") or "",
    }
    return info, bars


def _at(seq, i, default=None):
    try:
        value = seq[i]
    except (IndexError, TypeError):
        return default
    return default if value is None else value
