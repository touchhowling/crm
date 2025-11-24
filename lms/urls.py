from django.urls import path
from . import views

from django.contrib.auth import views as auth_views
from django.urls import path


urlpatterns = [
    # Leads
    path('leads/', views.leads_list, name='leads_list'),
    path('leads/add/', views.add_lead, name='add_lead'),
    path('leads/update-status/', views.update_lead_status, name='update_lead_status'),
    path('project/<int:project_id>/', views.lead_detail, name='lead_detail'),
    path('lead/<int:lead_id>/delete/', views.delete_lead, name='delete_lead'),
    path("boq/<int:boq_id>/update-invoice/", views.update_invoice_number, name="update_invoice_number"),
    path('projects/<int:project_id>/update-amount/', views.update_project_amount, name='update_project_amount'),
    # BOQ URLs
    path('projects/<project_id>/create-boq/', views.create_boq, name='create_boq'),
    path('boq/<int:boq_id>/view/', views.view_boq, name='view_boq'),
    path('boq/<int:boq_id>/download/', views.download_boq_pdf, name='download_boq_pdf'),
    path('boq/<int:boq_id>/update/', views.update_boq, name='update_boq'),
    path('boq/<int:boq_id>/delete/', views.delete_boq, name='delete_boq'),
    path('boq/<int:boq_id>/change-status/', views.change_boq_status, name='change_boq_status'),
    path('leads/search/', views.search_leads, name='search_leads'),
    path('projects/<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path('leads/add-inline/', views.add_inline_lead, name='add_inline_lead'),
    path('projects/<int:project_id>/boq/', views.project_boq_detail, name='project_boq_detail'),
    path('access-control/', views.access_control, name='access_control'),
    path('access-control/update/', views.update_user_groups, name='update_user_groups'),
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Projects
    path('ongoing_projects/', views.ongoing_projects, name='ongoing_projects'),
    path('project/<int:project_id>/', views.project_detail, name='project_detail'),
    path('project/add/', views.add_project, name='add_project'),
    path('projects/<int:project_id>/edit/', views.edit_project, name='edit_project'),

    # Tasks
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/add/', views.add_task, name='add_task'),
    path('tasks/toggle/<int:task_id>/', views.toggle_task, name='toggle_task'),
    path('task/<int:task_id>/', views.get_task, name='get_task'),
    path('task/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('task/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('task/<int:task_id>/complete/', views.mark_task_complete, name='mark_task_complete'),
    path('task/<int:task_id>/incomplete/', views.mark_task_incomplete, name='mark_task_incomplete'),
    
    # Inventory
    path('inventory/', views.inventory, name='inventory'),
    path('inventory/add/', views.add_inventory_item, name='add_inventory_item'),
    path('inventory/<int:item_id>/update/', views.update_inventory_item, name='update_inventory_item'),
    path('inventory/<int:item_id>/delete/', views.delete_inventory_item, name='delete_inventory_item'),
    path('inventory/upload-excel/', views.upload_inventory_excel, name='upload_inventory_excel'),
    path('api/inventory/<int:item_id>/requirements/', views.get_inventory_requirements, name='get_inventory_requirements'),
    path('projects/<int:project_id>/update-status/', views.update_project_status, name='update_project_status'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('notification/<int:notif_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notification/<int:notif_id>/delete/', views.delete_notification, name='delete_notification'),
    
    # Events/Calendar
    path('events/', views.events, name='events'),
    path('events/add/', views.add_event, name='add_event'),
    
    # API endpoints
    path('api/inventory/<int:item_id>/', views.get_inventory_item, name='get_inventory_item'),
    path('api/inventory/<int:item_id>/requirements/', views.get_inventory_requirements, name='get_inventory_requirements'),
    path('api/inventory/search/', views.search_inventory, name='search_inventory'),
    path('api/leads/summary/', views.api_leads_summary, name='api_leads_summary'),
    path('api/projects/summary/', views.api_projects_summary, name='api_projects_summary'),
    path('api/notification/count/', views.unread_notification_count, name='unread_notification_count'),

    path('change-password/', auth_views.PasswordChangeView.as_view(
        template_name='change_password.html',
        success_url='/password-changed/'
    ), name='change_password'),
    
    path('password-changed/', auth_views.PasswordChangeDoneView.as_view(
        template_name='password_changed.html'
    ), name='password_changed'),
]