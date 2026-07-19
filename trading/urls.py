from django.urls import path

from . import views

app_name = "trading"

urlpatterns = [
    path("", views.index, name="index"),
    path("run/", views.run_backtest_view, name="run_backtest"),
    path("import/yahoo/", views.import_yahoo_view, name="import_yahoo"),
    path("backtest/<int:pk>/", views.backtest_detail, name="backtest_detail"),
    path("stock/<str:symbol>/", views.stock_detail, name="stock_detail"),
    path("stock/<str:symbol>/compare/", views.compare_view, name="compare"),
]
