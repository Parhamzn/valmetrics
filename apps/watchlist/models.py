from __future__ import annotations
from django.db import models


class WatchlistItem(models.Model):
    ticker = models.CharField(max_length=16, unique=True)
    added_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["ticker"]

    def __str__(self):
        return self.ticker

    def save(self, *args, **kwargs):
        self.ticker = (self.ticker or "").strip().upper()
        super().save(*args, **kwargs)
