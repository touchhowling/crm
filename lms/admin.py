from django.contrib import admin
from .models import LeadSource, Project, Task, Event, Invoice, InventoryItem


@admin.register(LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
	list_display = ("first_name", "last_name", "country_code", "phone_number", "city", "snapshot_d")
	search_fields = ("first_name", "last_name", "phone_number", "city")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
	list_display = ("project_name", "amount", "status", "expected_closure", "snapshot_d")
	search_fields = ("project_name",)
	list_filter = ("status",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
	list_display = ("title", "project", "user", "due_date", "completed")
	search_fields = ("title",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
	list_display = ("start_datetime", "end_datetime", "user")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
	list_display = ("invoice_amount", "project", "snapshot_d")


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
	list_display = ("item_name", "unit_selling_price", "available_quantity")
