from django.contrib import admin
from .models import LeadSource, InventoryItem, Project, Task, Event, Invoice
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

class UserAdmin(BaseUserAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'phone_number', 'city', 'snapshot_d')
    list_filter = ('city', 'snapshot_d')
    search_fields = ('first_name', 'last_name', 'phone_number', 'city')
    ordering = ('-snapshot_d',)

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'unit_selling_price', 'available_quantity', 'quantity_to_be_ordered')
    search_fields = ('item_name',)

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_name', 'amount', 'status', 'lead_source', 'user', 'expected_closure')
    list_filter = ('status', 'expected_closure')
    search_fields = ('project_name', 'lead_source__first_name', 'lead_source__last_name')
    raw_id_fields = ('lead_source',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'user', 'due_date', 'completed')
    list_filter = ('completed', 'due_date')
    search_fields = ('title', 'description', 'project__project_name')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('start_datetime', 'end_datetime', 'user')
    list_filter = ('start_datetime',)
    search_fields = ('agenda',)

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_amount', 'project', 'item', 'snapshot_d')
    list_filter = ('snapshot_d',)
    search_fields = ('project__project_name',)
