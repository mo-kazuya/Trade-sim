# 株取引シミュレーター（Django バックテスト）

さまざまなアルゴリズムでの株式売買を、過去（またはシミュレートした）価格データに対して
**バックテスト**できる Django アプリケーションです。戦略ごとの資産推移・リターン・
最大ドローダウン・シャープレシオ・勝率などを計算し、Web 画面で比較できます。

## 主な機能

- **銘柄と価格データの管理**（OHLCV バー）— Django 管理画面から編集可能
- **5 種類の取引戦略**を同梱
  - Buy & Hold（買い持ち・比較基準）
  - 移動平均クロス（SMA Crossover / ゴールデン・デッドクロス）
  - RSI 逆張り
  - ボリンジャーバンド逆張り
  - MACD 順張り
- **バックテストエンジン**
  - 手数料率を考慮
  - ルックアヘッドバイアス回避のためシグナルは翌バーで約定
  - 指標: トータルリターン / Buy&Hold 比 / 最大ドローダウン / シャープレシオ / 取引回数 / 勝率
- **Web UI**
  - 戦略パラメータをフォームで指定して実行
  - 資産推移（エクイティカーブ）と売買ポイントをチャート表示（依存ライブラリ不要の自作 Canvas チャート）
  - 1 銘柄に対して全戦略を一括実行して比較・ランキング
- **合成価格データ生成コマンド**（オフラインでもすぐ試せます）

## セットアップ

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_data          # サンプル銘柄と合成価格データを生成
python manage.py runserver
```

ブラウザで <http://127.0.0.1:8000/> を開きます。

管理画面を使う場合は管理ユーザーを作成してください:

```bash
python manage.py createsuperuser
```

## 使い方

1. トップページで銘柄・戦略・パラメータ・初期資金・手数料率を指定して「実行する」
2. 結果ページで指標・資産推移チャート・取引履歴を確認
3. 銘柄ページの「全戦略で比較」から、同じ銘柄に対する各戦略の成績を並べて比較

`python manage.py seed_data` で生成される銘柄:

| シンボル | 特徴 |
|---------|------|
| TREND | 上昇トレンド |
| CHOPY | レンジ相場 |
| VOLTX | 高ボラティリティ |
| STEDY | 低ボラティリティ |

`--days` でバー数、`--reset` で既存データの削除ができます。

## 独自戦略の追加

`trading/strategies/implementations.py` に `Strategy` を継承したクラスを追加し、
`generate_positions(df)` で **目標ポジション（1=フル投資 / 0=現金）** の
pandas Series を返すだけです。作成したクラスを `trading/strategies/__init__.py` の
`STRATEGY_CLASSES` に登録すると、フォームと比較画面に自動で反映されます。

```python
class MyStrategy(Strategy):
    key = "my_strategy"
    label = "My Strategy"
    params = [Param("window", "期間", 20, "int", 2, 400)]

    def generate_positions(self, df):
        ma = df["close"].rolling(int(self.window)).mean()
        return (df["close"] > ma).astype(int)
```

## アーキテクチャ

```
config/            Django プロジェクト設定
trading/
  models.py        Stock / PriceBar / Backtest / Trade
  strategies/      戦略フレームワークと各アルゴリズム
  engine.py        バックテストエンジン（約定・指標計算）
  services.py      戦略実行と結果の永続化
  data.py          DataFrame 変換・合成データ生成
  views.py         画面（ダッシュボード / 結果 / 比較）
  templates/       HTML テンプレート
  static/          CSS と自作チャート（chart.js）
  management/commands/seed_data.py   サンプルデータ生成
```

## テスト

```bash
python manage.py test trading
```

エンジン・サービス・ビューのテストを収録しています。

## 実データについて

本アプリは既定で**合成データ**を用いるため、外部 API なしで動作します。
実際の株価を使う場合は、CSV から `PriceBar`（`date, open, high, low, close, volume`）を
取り込むか、任意のデータ提供元から取得して `PriceBar` を作成してください。

## 免責事項

本ソフトウェアは教育・研究目的のシミュレーションです。実際の投資判断や
投資助言を目的としたものではありません。
