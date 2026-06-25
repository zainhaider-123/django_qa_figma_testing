from django.urls import path

from . import views

app_name = "figma_auth"

urlpatterns = [
    path("status/", views.connection_status, name="status"),
    path("projects/", views.project_list, name="project_list"),
    path("projects/<str:project_id>/files/", views.file_list, name="file_list"),
    path("files/<str:file_key>/frames/", views.frame_tree, name="frame_tree"),
]
