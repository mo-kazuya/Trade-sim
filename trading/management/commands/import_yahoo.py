"""Download OHLCV data from Yahoo Finance and store it as PriceBars."""

from django.core.management.base import BaseCommand, CommandError

from trading.providers import VALID_INTERVALS, VALID_RANGES, DataProviderError
from trading.services import import_yahoo_data


class Command(BaseCommand):
    help = "Yahoo ファイナンスから価格データを取得して保存します。"

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+",
                            help="銘柄コード（例: AAPL 7203.T ^N225）")
        parser.add_argument("--range", dest="range_", default="1y",
                            choices=sorted(VALID_RANGES),
                            help="取得期間（既定: 1y）")
        parser.add_argument("--interval", default="1d",
                            choices=sorted(VALID_INTERVALS),
                            help="足の種類（既定: 1d）")

    def handle(self, *args, **options):
        for symbol in options["symbols"]:
            try:
                stock, created = import_yahoo_data(
                    symbol,
                    range_=options["range_"],
                    interval=options["interval"],
                )
            except (DataProviderError, ValueError) as exc:
                raise CommandError(f"{symbol}: {exc}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {stock.symbol}: {created} 本の新規バーを保存しました "
                    f"（合計 {stock.bar_count} 本）。"
                )
            )
        self.stdout.write(self.style.SUCCESS("取り込みが完了しました。"))
