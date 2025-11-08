from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from lms import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # AUTH
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # APP
    path('', include('lms.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)