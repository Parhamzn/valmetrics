from django.urls import path
from . import views

app_name = "watchlist"

urlpatterns = [
    path("", views.list_view, name="list"),
    path("add/", views.add, name="add"),
    path("remove/", views.remove, name="remove"),
    path("items/<int:item_id>/notes/", views.update_notes, name="update_notes"),
]
