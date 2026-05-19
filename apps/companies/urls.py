from django.urls import path

from . import views

app_name = "companies"

urlpatterns = [
    path("", views.home, name="home"),
    path("company/", views.search, name="search_legacy"),
    path("search/", views.search, name="search"),
    path("company/<str:ticker>/", views.company_root, name="root"),
    path("company/<str:ticker>/overview/", views.overview, name="overview"),
    path("company/<str:ticker>/income-statement/", views.income_statement, name="income"),
    path("company/<str:ticker>/balance-sheet/", views.balance_sheet, name="balance"),
    path("company/<str:ticker>/cash-flow/", views.cash_flow, name="cashflow"),
    path("company/<str:ticker>/ratios/", views.ratios, name="ratios"),
]
