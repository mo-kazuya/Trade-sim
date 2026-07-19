from django import forms

from .models import Stock
from .strategies import STRATEGY_CLASSES


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
