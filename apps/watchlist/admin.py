from django.contrib import admin
from .models import WatchlistItem


@admin.register(WatchlistItem)
class WatchlistItemAdmin(admin.ModelAdmin):
    list_display = ("ticker", "added_at", "notes")
    search_fields = ("ticker", "notes")
