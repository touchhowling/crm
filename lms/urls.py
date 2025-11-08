from django.urls import path
from . import views

urlpatterns = [
    path('leads/', views.leads_list, name='leads_list'),
    path('leads/add/', views.add_lead, name='add_lead'),
    path('leads/update-status/', views.update_lead_status, name='update_lead_status'),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    path('ongoing_projects/', views.ongoing_projects, name='ongoing_projects'),
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/add/', views.add_task, name='add_task'),
    path('tasks/toggle/<int:task_id>/', views.toggle_task, name='toggle_task'),
    path('inventory/', views.inventory, name='inventory'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('task/<int:task_id>/complete/', views.mark_task_complete, name='mark_task_complete'),
    path('task/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('task/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('task/<int:task_id>/incomplete/', views.mark_task_incomplete, name='mark_task_incomplete'),
    path('task/<int:task_id>/', views.get_task, name='get_task'),
]