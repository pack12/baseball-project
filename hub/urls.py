from django.urls import path

from . import views

app_name = "hub"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("players/<int:mlbam_id>/", views.player_detail, name="player"),
    path("leaderboards/", views.leaderboard, name="leaderboard"),
]
