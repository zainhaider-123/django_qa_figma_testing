from django.urls import path

from qa import views

app_name = "qa"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("new/", views.new_run, name="new_run"),
    path("runs/", views.run_list, name="run_list"),
    path("run/<int:run_id>/", views.run_report, name="run_report"),
    path("run/<int:run_id>/rerun/", views.rerun, name="rerun"),
]
