"""URL configuration for the local flight comparison MVP."""

from django.urls import path

from flights.web.views import search_view


urlpatterns = [
    path("", search_view, name="flight-search"),
]
