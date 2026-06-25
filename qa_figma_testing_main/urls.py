from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('figma/', include('figma_auth.urls')),
    path('qa/', include('qa.urls')),
    path('', RedirectView.as_view(url='/qa/'), name='home'),
]
