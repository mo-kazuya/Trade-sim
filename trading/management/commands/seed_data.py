"""Populate the database with synthetic stocks and price history for demos."""

from django.core.management.base import BaseCommand
from django.db import transaction

from trading.data import generate_synthetic_ohlc
from trading.models import PriceBar, Stock

# (symbol, name, seed, start_price, drift, vol)
SAMPLE_STOCKS = [
    ("TREND", "Trend Industries（上昇トレンド）", 1, 100.0, 0.18, 0.22),
    ("CHOPY", "Choppy Corp（レンジ相場）", 2, 80.0, 0.02, 0.30),
    ("VOLTX", "Voltex Energy（高ボラティリティ）", 3, 120.0, 0.10, 0.45),
    ("STEDY", "Steady Foods（低ボラティリティ）", 4, 60.0, 0.06, 0.12),
]


class Command(BaseCommand):
    help = "サンプルの銘柄と合成価格データを生成します。"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=750,
                            help="生成する営業日数（既定: 750）")
        parser.add_argument("--reset", action="store_true",
                            help="既存のデータを削除してから生成します。")

    @transaction.atomic
    def handle(self, *args, **options):
        days = options["days"]
        if options["reset"]:
            Stock.objects.all().delete()
            self.stdout.write(self.style.WARNING("既存の銘柄をすべて削除しました。"))

        for symbol, name, seed, price, drift, vol in SAMPLE_STOCKS:
            stock, created = Stock.objects.get_or_create(
                symbol=symbol, defaults={"name": name}
            )
            if not created and stock.bars.exists():
                self.stdout.write(f"  {symbol}: 既にデータあり。スキップします。")
                continue
            stock.name = name
            stock.save()

            bars = generate_synthetic_ohlc(
                days=days, start_price=price, annual_drift=drift,
                annual_vol=vol, seed=seed,
            )
            PriceBar.objects.bulk_create(
                [PriceBar(stock=stock, **bar) for bar in bars]
            )
            self.stdout.write(
                self.style.SUCCESS(f"  {symbol}: {len(bars)} 本のバーを生成しました。")
            )

        self.stdout.write(self.style.SUCCESS("シードデータの生成が完了しました。"))
