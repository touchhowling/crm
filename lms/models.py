from django.db import models
from django.conf import settings

class LeadSource(models.Model):
    # Split phone into country code and number. Make phone_number required.
    country_code = models.CharField(max_length=6, blank=False, null=False, default='+91')
    phone_number = models.CharField(max_length=10, blank=False, null=False)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    snapshot_d = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.country_code}{self.phone_number}"

class InventoryItem(models.Model):
    item_name = models.CharField(max_length=200)
    unit_selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    available_quantity = models.IntegerField(default=0)
    quantity_to_be_ordered = models.IntegerField(default=0)
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.item_name

class Project(models.Model):
    project_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    expected_closure = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=100, default="open")
    lead_source = models.ForeignKey(LeadSource, on_delete=models.SET_NULL, null=True, blank=False)
    remarks = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.project_name

class Task(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class Event(models.Model):
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(blank=True, null=True)
    agenda = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    snapshot_d = models.DateTimeField(auto_now=True)

class Invoice(models.Model):
    invoice_amount = models.DecimalField(max_digits=12, decimal_places=2)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invoices")
    item = models.ForeignKey(InventoryItem, on_delete=models.SET_NULL, null=True, blank=True)
    snapshot_d = models.DateTimeField(auto_now=True)
