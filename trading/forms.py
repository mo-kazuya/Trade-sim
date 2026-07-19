from django import forms

from .models import Stock
from .providers import VALID_INTERVALS, VALID_RANGES
from .strategies import STRATEGY_CLASSES


class YahooImportForm(forms.Form):
    symbol = forms.CharField(
        label="銘柄コード", max_length=20,
        help_text="例: AAPL（米国株）／ 7203.T（トヨタ）／ ^N225（日経平均）",
    )
    range_ = forms.ChoiceField(
        label="取得期間",
        choices=[(r, r) for r in ["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"]],
        initial="2y",
    )
    interval = forms.ChoiceField(
        label="足の種類",
        choices=[("1d", "日足"), ("1wk", "週足"), ("1mo", "月足")],
        initial="1d",
    )

    def clean_range_(self):
        value = self.cleaned_data["range_"]
        if value not in VALID_RANGES:
            raise forms.ValidationError("無効な期間です。")
        return value

    def clean_interval(self):
        value = self.cleaned_data["interval"]
        if value not in VALID_INTERVALS:
            raise forms.ValidationError("無効な足種別です。")
        return value


class BacktestForm(forms.Form):
    stock = forms.ModelChoiceField(
        queryset=Stock.objects.all(), label="銘柄"
    )
    strategy = forms.ChoiceField(
        choices=[(c.key, c.label) for c in STRATEGY_CLASSES], label="戦略"
    )
    initial_cash = forms.FloatField(
        label="初期資金", initial=100_000, min_value=1
    )
    commission = forms.FloatField(
        label="手数料率", initial=0.001, min_value=0, max_value=0.1,
        help_text="1回の取引ごとにかかる手数料の割合（例: 0.001 = 0.1%）",
    )

    def clean(self):
        cleaned = super().clean()
        # Strategy-specific parameters are validated in the view against the
        # selected strategy's Param definitions.
        return cleaned
