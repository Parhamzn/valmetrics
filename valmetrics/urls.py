from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.companies.urls')),
    path('', include('apps.valuation.urls')),
    path('watchlist/', include('apps.watchlist.urls')),
]
