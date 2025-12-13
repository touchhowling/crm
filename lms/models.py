from datetime import datetime
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class LeadSource(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('contacted', 'Contacted'),
        ('boq', 'BOQ'),
        ('advance', 'Advance'),
        ('won', 'Won'),
        ('lost', 'Lost'),
    ]
    
    country_code = models.CharField(max_length=6, blank=False, null=False, default='+91')
    phone_number = models.CharField(max_length=10, blank=False, null=False)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    snapshot_d = models.DateTimeField(auto_now_add=True)
    has_project = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.country_code}{self.phone_number}"

    class Meta:
        verbose_name = 'Lead Source'
        verbose_name_plural = 'Lead Sources'
        ordering = ['-snapshot_d']


class InventoryItem(models.Model):
    item_name = models.CharField(max_length=200)
    unit_selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    available_quantity = models.IntegerField(default=0)
    quantity_to_be_ordered = models.IntegerField(default=0)
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.item_name

    @property
    def is_low_stock(self):
        """Returns True if stock is below 10 units"""
        return self.available_quantity < 10


class Project(models.Model):
    project_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    expected_closure = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=100, default="In Progress")
    lead_source = models.ForeignKey(LeadSource, on_delete=models.SET_NULL, null=True, blank=False)
    remarks = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    snapshot_d = models.DateTimeField(auto_now=True)
    city = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.project_name


class BOQ(models.Model):
    """Bill of Quantity for a lead"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    lead_source = models.ForeignKey(LeadSource, on_delete=models.CASCADE, related_name='boqs')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='boqs')
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    
    # Tax settings
    tax_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=18.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Tax rate in percentage (default: 18% GST)"
    )
    
    # Discount settings
    overall_discount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Overall discount amount"
    )
    overall_discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall discount in percentage"
    )
    
    # Calculated fields
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'BOQ'
        verbose_name_plural = 'BOQs'
    
    def __str__(self):
        return f"{self.invoice_number} - {self.lead_source}"
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number: INV-YYYYMMDD-XXXX
            from django.db.models import Max
            today = datetime.now().strftime('%Y%m%d')
            last_invoice = BOQ.objects.filter(
                invoice_number__startswith=f'INV-{today}'
            ).aggregate(Max('invoice_number'))
            
            if last_invoice['invoice_number__max']:
                last_number = int(last_invoice['invoice_number__max'].split('-')[-1])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.invoice_number = f'INV-{today}-{new_number:04d}'
        
        super().save(*args, **kwargs)
    
    def calculate_totals(self):
        """Calculate all totals for the BOQ"""
        items = self.items.all()
        
        # Calculate subtotal (sum of gross amounts BEFORE discounts)
        subtotal = Decimal('0')
        item_discounts_total = Decimal('0')
        
        for item in items:
            gross_amount = Decimal(str(item.unit_price)) * Decimal(str(item.quantity))
            subtotal += gross_amount
            item_discounts_total += Decimal(str(item.discount_amount))
        
        self.subtotal = subtotal
        
        # Amount after item discounts
        amount_after_item_discounts = subtotal - item_discounts_total
        
        # Calculate overall discount
        if self.overall_discount_percentage > 0:
            self.overall_discount = (amount_after_item_discounts * Decimal(str(self.overall_discount_percentage))) / Decimal('100')
        else:
            self.overall_discount = Decimal('0')
        
        # Amount after all discounts
        amount_after_all_discounts = amount_after_item_discounts - self.overall_discount
        
        # Calculate tax on discounted amount
        self.total_tax = (amount_after_all_discounts * Decimal(str(self.tax_rate))) / Decimal('100')
        
        # Total discount (item discounts + overall discount)
        self.total_discount = item_discounts_total + self.overall_discount
        
        # Calculate grand total
        self.grand_total = amount_after_all_discounts + self.total_tax
        
        self.save()


class BOQItem(models.Model):
    """Individual items in a BOQ"""
    boq = models.ForeignKey(BOQ, on_delete=models.CASCADE, related_name='items')
    sr_no = models.IntegerField()
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    
    # Item details (stored for historical record)
    item_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    
    # Discount
    discount_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Calculated fields
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Inventory check
    has_sufficient_stock = models.BooleanField(default=True)
    available_quantity = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['sr_no']
        unique_together = ['boq', 'sr_no']
    
    def __str__(self):
        return f"{self.sr_no}. {self.item_name}"
    
    def save(self, *args, **kwargs):
        # Store current inventory details
        self.item_name = self.inventory_item.item_name
        self.unit_price = Decimal(str(self.inventory_item.unit_selling_price))
        self.available_quantity = self.inventory_item.available_quantity
        
        # Check stock availability
        self.has_sufficient_stock = self.available_quantity >= self.quantity
        
        # Calculate discount amount
        gross_amount = self.unit_price * Decimal(str(self.quantity))
        
        if self.discount_percentage > 0:
            self.discount_amount = (gross_amount * Decimal(str(self.discount_percentage))) / Decimal('100')
        else:
            self.discount_amount = Decimal('0')
        
        # Calculate line total (after discount, before tax)
        self.line_total = gross_amount - self.discount_amount
        
        super().save(*args, **kwargs)
        
        # Update inventory order requirement
        if not self.has_sufficient_stock:
            shortage = self.quantity - self.available_quantity
            current_to_order = self.inventory_item.quantity_to_be_ordered
            self.inventory_item.quantity_to_be_ordered = current_to_order + shortage
            self.inventory_item.save()
        
        # Recalculate BOQ totals
        self.boq.calculate_totals()


class InventoryOrderRequirement(models.Model):
    """Track which inventory items need to be ordered for which projects"""
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='order_requirements')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='inventory_requirements')
    boq = models.ForeignKey(BOQ, on_delete=models.CASCADE, related_name='inventory_requirements')
    boq_item = models.ForeignKey(BOQItem, on_delete=models.CASCADE, related_name='order_requirement')
    
    required_quantity = models.IntegerField()
    available_quantity = models.IntegerField()
    shortage_quantity = models.IntegerField()
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('ordered', 'Ordered'),
            ('received', 'Received'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )
    
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Inventory Order Requirement'
        verbose_name_plural = 'Inventory Order Requirements'
    
    def __str__(self):
        return f"{self.inventory_item.item_name} - {self.project.project_name} (Need: {self.shortage_quantity})"


class Task(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name="tasks_assigned_to"
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="tasks_assigned_by"
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(default=datetime.now)
    completed = models.BooleanField(default=False)
    priority = models.CharField(
        max_length=10,
        choices=[("High", "High"), ("Medium", "Medium"), ("Low", "Low")],
        default="Medium",
    )
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        """Returns True if task not completed and before due date"""
        from django.utils import timezone
        return not self.completed and self.due_date > timezone.now()

    @property
    def is_pending(self):
        """Returns True if task not completed and due date has passed"""
        from django.utils import timezone
        return not self.completed and self.due_date <= timezone.now()


class Event(models.Model):
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(blank=True, null=True)
    agenda = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.agenda[:50]} - {self.start_datetime.strftime('%Y-%m-%d')}"


class Invoice(models.Model):
    invoice_amount = models.DecimalField(max_digits=12, decimal_places=2)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invoices")
    item = models.ForeignKey(InventoryItem, on_delete=models.SET_NULL, null=True, blank=True)
    snapshot_d = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice {self.id} - {self.project.project_name}"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.message


class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task.title} assigned to {self.user.username}"