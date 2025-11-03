from django.urls import path
from . import views

urlpatterns = [
    path('leads/', views.leads_list, name='leads_list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('ongoing_projects/', views.ongoing_projects, name='ongoing_projects'),
    path('tasks/', views.tasks, name='tasks'),
    path('inventory/', views.inventory, name='inventory'),
]
