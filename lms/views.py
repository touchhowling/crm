# lms/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from httpx import request
from .models import LeadSource, InventoryItem, Project, Task, Event, Invoice,Notification
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count ,Sum
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import Group
from django.http import JsonResponse
from .models import LeadSource
import json
from django.http import HttpResponseRedirect
from django.urls import reverse



@csrf_exempt
def add_inline_lead(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        country_code = data.get('country_code', '+91')
        phone_number = data.get('phone_number')
        city = data.get('city')
        address = data.get('address')

        if not first_name or not phone_number:
            return JsonResponse({'success': False, 'message': 'First name and phone number are required!'})

        # Create lead
        lead = LeadSource.objects.create(
            first_name=first_name,
            last_name=last_name,
            country_code=country_code,
            phone_number=phone_number,
            city=city,
            address=address,
        )

        return JsonResponse({
            'success': True,
            'message': 'Lead created successfully',
            'id': lead.id,
            'first_name': lead.first_name,
            'last_name': lead.last_name,
        })

def search_leads(request):
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    leads = LeadSource.objects.filter(
        first_name__icontains=query
    ) | LeadSource.objects.filter(
        last_name__icontains=query
    ) | LeadSource.objects.filter(
        phone_number__icontains=query
    )

    data = list(leads.values('id', 'first_name', 'last_name', 'city'))
    return JsonResponse(data, safe=False)


# ============================================================================
# AUTHENTICATION VIEWS
def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('leads_list')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            return redirect('leads_list')
        else:
            messages.error(request, 'Invalid username or password!')
            return render(request, 'registration/login.html')
    
    return render(request, 'registration/login.html')


def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully!')
    return redirect('login')


# ============================================================================
# LEAD VIEWS
# ============================================================================

@login_required
def leads_list(request):
    """Display list of all leads with search and filter capabilities"""

    if request.user.is_superuser or request.user.groups.filter(name="admin").exists():
        leads = LeadSource.objects.all().order_by('-snapshot_d')
        projects = Project.objects.select_related('lead_source').all()
    else:
        leads = LeadSource.objects.filter(user=request.user).order_by('-snapshot_d')
        projects = Project.objects.filter(user=request.user).order_by('-snapshot_d')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        leads = leads.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(city__icontains=search_query)
        )
    
    # Filter by city
    city_filter = request.GET.get('city', '')
    if city_filter:
        leads = leads.filter(city=city_filter)
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        leads = leads.filter(status=status_filter)
    
    context = {
        'leads': leads,
        'search_query': search_query,
        'city_filter': city_filter,
        'status_filter': status_filter,
        'projects': projects
    }
    
    return render(request, 'lms/leads_list.html', context)


@login_required
@require_POST
def add_lead(request):
    """Add a new lead"""
    try:
        country_code = request.POST.get('country_code', '+91').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        city = request.POST.get('city', '').strip()
        address = request.POST.get('address', '').strip()
        remarks = request.POST.get('remarks', '').strip()
        status = request.POST.get('status', 'open')
        
        # Validation
        if not phone_number or not first_name:
            messages.error(request, 'Phone number and first name are required!')
            return redirect('leads_list')
        
        if len(phone_number) != 10 or not phone_number.isdigit():
            messages.error(request, 'Phone number must be exactly 10 digits!')
            return redirect('leads_list')
        
        # Check for duplicate phone number
        if LeadSource.objects.filter(country_code=country_code, phone_number=phone_number).exists():
            messages.error(request, 'A lead with this phone number already exists!')
            return redirect('leads_list')
        
        # Create new lead
        lead = LeadSource.objects.create(
            country_code=country_code,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            city=city,
            address=address,
            remarks=remarks,
            status=status,
            user=request.user
        )
        
        messages.success(request, f'Lead "{first_name} {last_name}" added successfully!')
        return redirect('leads_list')
        
    except Exception as e:
        messages.error(request, f'Error adding lead: {str(e)}')
        return redirect('leads_list')


@login_required
@require_POST
def update_lead_status(request):
    """Update lead status via AJAX"""
    try:
        lead_id = request.POST.get('lead_id')
        new_status = request.POST.get('status')
        
        if not lead_id or not new_status:
            return JsonResponse({
                'success': False,
                'message': 'Lead ID and status are required!'
            }, status=400)
        
        lead = get_object_or_404(LeadSource, id=lead_id)
        
        # Validate status
        valid_statuses = ['open', 'contacted', 'boq', 'advanced', 'won', 'closed', 'lost']
        if new_status not in valid_statuses:
            return JsonResponse({
                'success': False,
                'message': 'Invalid status value!'
            }, status=400)
        
        lead.status = new_status
        lead.save()
        
        # Auto-create project when status becomes "advanced"
        if new_status == 'advanced' and not lead.has_project:
            project_name = f"{lead.first_name} {lead.last_name} - {lead.city or 'Project'}"
            Project.objects.create(
                project_name=project_name,
                lead_source=lead,
                status='In Progress',
                user=request.user
            )
            lead.has_project = True
            lead.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Status updated to {new_status.upper()} successfully!'
        })
        
    except LeadSource.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Lead not found!'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)
@login_required
def lead_detail(request, lead_id):
    """Display detailed information about a specific lead"""
    lead = get_object_or_404(LeadSource, id=lead_id)
    projects = Project.objects.filter(lead_source=lead).order_by('-snapshot_d')
    
    context = {
        'lead': lead,
        'projects': projects,
    }
    
    return render(request, 'lms/lead_detail.html', context)


@login_required
@require_POST
def delete_lead(request, lead_id):
    """Delete a lead"""
    try:
        lead = get_object_or_404(LeadSource, id=lead_id)
        lead_name = f"{lead.first_name} {lead.last_name}"
        lead.delete()
        
        messages.success(request, f'Lead "{lead_name}" deleted successfully!')
        return redirect('leads_list')
        
    except Exception as e:
        messages.error(request, f'Error deleting lead: {str(e)}')
        return redirect('leads_list')


# ============================================================================
# DASHBOARD VIEW
# ============================================================================
# Add these imports at the top of views.py
from django.http import HttpResponse
from django.template.loader import get_template
from io import BytesIO
from .models import BOQ, BOQItem, InventoryOrderRequirement

# For PDF generation, install: pip install xhtml2pdf reportlab
try:
    from xhtml2pdf import pisa
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: xhtml2pdf not installed. PDF generation will not work.")


@login_required
def lead_detail(request, lead_id):
    """Display detailed information about a specific lead with BOQ functionality"""
    lead = get_object_or_404(LeadSource, id=lead_id)
    
    # Check permissions
    if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
        if lead.user != request.user:
            messages.error(request, 'You do not have permission to view this lead.')
            return redirect('leads_list')
    
    projects = Project.objects.filter(lead_source=lead).order_by('-snapshot_d')
    boqs = BOQ.objects.filter(lead_source=lead).order_by('-created_at')
    inventory_items = InventoryItem.objects.all().order_by('item_name')
    
    context = {
        'lead': lead,
        'projects': projects,
        'boqs': boqs,
        'inventory_items': inventory_items,
    }
    
    return render(request, 'lms/lead_detail.html', context)


@login_required
@require_POST
def create_boq(request, lead_id):
    """Create a new BOQ for a lead - FIXED VERSION"""
    from decimal import Decimal
    
    try:
        lead = get_object_or_404(LeadSource, id=lead_id)
        
        # Get form data
        tax_rate = Decimal(request.POST.get('tax_rate', '18.00'))
        overall_discount_percentage = Decimal(request.POST.get('overall_discount_percentage', '0'))
        notes = request.POST.get('notes', '')
        
        # Create BOQ
        boq = BOQ.objects.create(
            lead_source=lead,
            tax_rate=tax_rate,
            overall_discount_percentage=overall_discount_percentage,
            notes=notes,
            created_by=request.user
        )
        
        # Get item data (arrays)
        sr_nos = request.POST.getlist('sr_no[]')
        inventory_ids = request.POST.getlist('inventory_id[]')
        quantities = request.POST.getlist('quantity[]')
        discounts = request.POST.getlist('discount[]')
        
        # Validation
        valid_items = [i for i, inv_id in enumerate(inventory_ids) if inv_id and inv_id.strip()]
        
        if not valid_items:
            boq.delete()
            messages.error(request, 'Please add at least one item to the BOQ!')
            return redirect('lead_detail', lead_id=lead_id)
        
        # Create BOQ items
        items_created = 0
        for i in valid_items:
            try:
                inventory_item = get_object_or_404(InventoryItem, id=int(inventory_ids[i]))
                quantity = int(quantities[i])
                discount = Decimal(discounts[i]) if discounts[i] else Decimal('0')
                
                # Create the BOQ item
                boq_item = BOQItem.objects.create(
                    boq=boq,
                    sr_no=int(sr_nos[i]),
                    inventory_item=inventory_item,
                    quantity=quantity,
                    discount_percentage=discount
                )
                items_created += 1
                
                # Create order requirement if insufficient stock
                if not boq_item.has_sufficient_stock:
                    shortage = quantity - boq_item.available_quantity
                    
                    # Get or create project
                    project = boq.project
                    if not project:
                        project_name = f"{lead.first_name} {lead.last_name} - {lead.city or 'Project'}"
                        project = Project.objects.create(
                            project_name=project_name,
                            lead_source=lead,
                            amount=Decimal('0'),  # Will be updated after BOQ calculation
                            status='In Progress',
                            user=request.user
                        )
                        boq.project = project
                        boq.save()
                    
                    # Create order requirement
                    InventoryOrderRequirement.objects.create(
                        inventory_item=inventory_item,
                        project=project,
                        boq=boq,
                        boq_item=boq_item,
                        required_quantity=quantity,
                        available_quantity=boq_item.available_quantity,
                        shortage_quantity=shortage,
                        status='pending'
                    )
                    
            except Exception as e:
                messages.warning(request, f'Error adding item {i+1}: {str(e)}')
                continue
        
        if items_created == 0:
            boq.delete()
            messages.error(request, 'Failed to create any BOQ items!')
            return redirect('lead_detail', lead_id=lead_id)
        
        # Calculate totals
        boq.calculate_totals()
        
        # Reload BOQ to get updated values
        boq.refresh_from_db()
        
        # Update lead status to BOQ if not already advanced or won
        if lead.status not in ['advanced', 'won', 'closed']:
            lead.status = 'boq'
            lead.save()
        
        # Create or update project
        if not lead.has_project:
            project_name = f"{lead.first_name} {lead.last_name} - {lead.city or 'Project'}"
            project = Project.objects.create(
                project_name=project_name,
                lead_source=lead,
                amount=boq.grand_total,
                status='In Progress',
                user=request.user
            )
            boq.project = project
            boq.save()
            lead.has_project = True
            lead.save()
        elif boq.project:
            # Update existing project amount
            boq.project.amount = boq.grand_total
            boq.project.save()
        
        messages.success(request, f'BOQ {boq.invoice_number} created successfully with {items_created} items!')
        return redirect('view_boq', boq_id=boq.id)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f'Error creating BOQ: {str(e)}')
        return redirect('lead_detail', lead_id=lead_id)

@login_required
def edit_project(request, project_id):
    """Edit an existing project"""
    try:
        project = get_object_or_404(Project, id=project_id)

        # Access control: only the assigned user, admin, or superuser can edit
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if project.user != request.user:
                messages.error(request, 'You do not have permission to edit this project!')
                referer = request.META.get('HTTP_REFERER')
                return HttpResponseRedirect(referer or reverse('ongoing_projects'))

        if request.method == 'POST':
            project_name = request.POST.get('project_name', '').strip()
            amount = request.POST.get('amount', '').strip()
            expected_closure = request.POST.get('expected_closure', '').strip()
            status = request.POST.get('status', 'open')
            remarks = request.POST.get('remarks', '').strip()
            lead_source_id = request.POST.get('lead_source_id', '').strip()

            # Validation
            if not project_name or not lead_source_id:
                messages.error(request, 'Project name and lead source are required!')
                return redirect('edit_project', project_id=project_id)

            lead_source = get_object_or_404(LeadSource, id=lead_source_id)

            # Update project details
            project.project_name = project_name
            project.amount = amount if amount else None
            project.expected_closure = expected_closure if expected_closure else None
            project.status = status
            project.lead_source = lead_source
            project.remarks = remarks
            project.save()

            messages.success(request, f'Project "{project_name}" updated successfully!')
            referer = request.META.get('HTTP_REFERER')
            return HttpResponseRedirect(referer or reverse('ongoing_projects'))

        # For GET request → prefill the form
        lead_sources = LeadSource.objects.all().order_by('first_name')
        context = {
            'project': project,
            'lead_sources': lead_sources
        }
        return render(request, 'lms/edit_project.html', context)

    except Exception as e:
        messages.error(request, f'Error editing project: {str(e)}')
        referer = request.META.get('HTTP_REFERER')
        return HttpResponseRedirect(referer or reverse('ongoing_projects'))

@login_required
def delete_project(request, project_id):
    """Delete a project"""
    try:
        project = get_object_or_404(Project, id=project_id)

        # Access control
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if project.user != request.user:
                messages.error(request, 'You do not have permission to delete this project!')
                referer = request.META.get('HTTP_REFERER')
                return HttpResponseRedirect(referer or reverse('ongoing_projects'))
        project_name = project.project_name
        project.delete()

        messages.success(request, f'Project "{project_name}" deleted successfully!')
        referer = request.META.get('HTTP_REFERER')
        return HttpResponseRedirect(referer or reverse('ongoing_projects'))

    except Exception as e:
        messages.error(request, f'Error deleting project: {str(e)}')
        referer = request.META.get('HTTP_REFERER')
        return HttpResponseRedirect(referer or reverse('ongoing_projects'))
    
@login_required
@require_POST
def update_boq(request, boq_id):
    """Update an existing BOQ - FIXED VERSION"""
    from decimal import Decimal
    
    try:
        boq = get_object_or_404(BOQ, id=boq_id)
        
        # Check if user has permission
        if boq.status == 'approved':
            messages.error(request, 'Cannot edit approved BOQ!')
            return redirect('view_boq', boq_id=boq_id)
        
        # Check permissions
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if boq.created_by != request.user:
                messages.error(request, 'You do not have permission to edit this BOQ.')
                return redirect('view_boq', boq_id=boq_id)
        
        # Update BOQ fields
        boq.tax_rate = Decimal(request.POST.get('tax_rate', '18.00'))
        boq.overall_discount_percentage = Decimal(request.POST.get('overall_discount_percentage', '0'))
        boq.notes = request.POST.get('notes', '')
        boq.save()
        
        # Delete existing items and order requirements
        boq.items.all().delete()
        InventoryOrderRequirement.objects.filter(boq=boq).delete()
        
        # Create new items
        sr_nos = request.POST.getlist('sr_no[]')
        inventory_ids = request.POST.getlist('inventory_id[]')
        quantities = request.POST.getlist('quantity[]')
        discounts = request.POST.getlist('discount[]')
        
        valid_items = [i for i, inv_id in enumerate(inventory_ids) if inv_id and inv_id.strip()]
        items_created = 0
        
        for i in valid_items:
            try:
                inventory_item = get_object_or_404(InventoryItem, id=int(inventory_ids[i]))
                quantity = int(quantities[i])
                discount = Decimal(discounts[i]) if discounts[i] else Decimal('0')
                
                boq_item = BOQItem.objects.create(
                    boq=boq,
                    sr_no=int(sr_nos[i]),
                    inventory_item=inventory_item,
                    quantity=quantity,
                    discount_percentage=discount
                )
                items_created += 1
                
                # Create order requirement if insufficient stock
                if not boq_item.has_sufficient_stock:
                    shortage = quantity - boq_item.available_quantity
                    
                    if boq.project:
                        InventoryOrderRequirement.objects.create(
                            inventory_item=inventory_item,
                            project=boq.project,
                            boq=boq,
                            boq_item=boq_item,
                            required_quantity=quantity,
                            available_quantity=boq_item.available_quantity,
                            shortage_quantity=shortage,
                            status='pending'
                        )
            except Exception as e:
                messages.warning(request, f'Error adding item {i+1}: {str(e)}')
                continue
        
        # Recalculate totals
        boq.calculate_totals()
        
        # Reload BOQ
        boq.refresh_from_db()
        
        # Update project amount if exists
        if boq.project:
            boq.project.amount = boq.grand_total
            boq.project.save()
        
        messages.success(request, f'BOQ {boq.invoice_number} updated successfully with {items_created} items!')
        return redirect('view_boq', boq_id=boq_id)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f'Error updating BOQ: {str(e)}')
        return redirect('view_boq', boq_id=boq_id)

@login_required
def view_boq(request, boq_id):
    """View BOQ details"""
    boq = get_object_or_404(BOQ, id=boq_id)
    
    # Check permissions
    if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
        if boq.lead_source.user != request.user:
            messages.error(request, 'You do not have permission to view this BOQ.')
            return redirect('leads_list')
    
    items = boq.items.all().order_by('sr_no')
    
    context = {
        'boq': boq,
        'items': items,
    }
    
    return render(request, 'lms/view_boq.html', context)


@login_required
def download_boq_pdf(request, boq_id):
    """Generate and download BOQ as PDF"""
    if not PDF_AVAILABLE:
        messages.error(request, 'PDF generation is not available. Please install xhtml2pdf.')
        return redirect('view_boq', boq_id=boq_id)
    
    boq = get_object_or_404(BOQ, id=boq_id)
    items = boq.items.all().order_by('sr_no')
    
    # Prepare context
    context = {
        'boq': boq,
        'items': items,
        'company_name': 'SecureTech AV',
        'company_address': 'Your Company Address Here',
        'company_phone': '+91-XXXXXXXXXX',
        'company_email': 'info@securetechav.com',
        'company_gst': 'GSTIN: XXXXXXXXXXXX',
    }
    
    # Render template
    template = get_template('lms/boq_pdf_template.html')
    html = template.render(context)
    
    # Create PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="BOQ_{boq.invoice_number}.pdf"'
    
    # Generate PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        messages.error(request, 'Error generating PDF')
        return redirect('view_boq', boq_id=boq_id)
    
    return response
# Add these missing functions to your lms/views.py file


@login_required
def get_inventory_item(request, item_id):
    """API endpoint to get inventory item details"""
    try:
        item = get_object_or_404(InventoryItem, id=item_id)
        return JsonResponse({
            'success': True,
            'item': {
                'id': item.id,
                'name': item.item_name,
                'price': float(item.unit_selling_price),
                'available_quantity': item.available_quantity
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=404)


@login_required
def search_inventory(request):
    """API endpoint to search inventory items"""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return JsonResponse({'items': []})
    
    items = InventoryItem.objects.filter(
        item_name__icontains=query
    )[:10]
    
    results = [{
        'id': item.id,
        'name': item.item_name,
        'price': float(item.unit_selling_price),
        'available_quantity': item.available_quantity
    } for item in items]
    
    return JsonResponse({'items': results})


# Add/Replace this function in your lms/views.py

@login_required
def get_inventory_requirements(request, item_id):
    """API endpoint to get inventory requirements by project - FIXED VERSION"""
    try:
        item = get_object_or_404(InventoryItem, id=item_id)
        
        # Get all order requirements for this item
        requirements = InventoryOrderRequirement.objects.filter(
            inventory_item=item
        ).select_related('project', 'boq', 'boq_item').order_by('-created_at')
        
        # Calculate total required across all projects
        total_required = sum(r.shortage_quantity for r in requirements)
        
        # Build response data
        requirements_list = []
        for req in requirements:
            requirements_list.append({
                'id': req.id,
                'project_name': req.project.project_name if req.project else 'N/A',
                'project_id': req.project.id if req.project else None,
                'boq_number': req.boq.invoice_number if req.boq else 'N/A',
                'boq_id': req.boq.id if req.boq else None,
                'required_qty': req.required_quantity,
                'available_qty': req.available_quantity,
                'shortage_qty': req.shortage_quantity,
                'status': req.status,
                'status_display': dict([
                    ('pending', 'Pending'),
                    ('ordered', 'Ordered'),
                    ('received', 'Received'),
                    ('cancelled', 'Cancelled'),
                ]).get(req.status, req.status),
                'created_at': req.created_at.strftime('%Y-%m-%d %H:%M'),
                'notes': req.notes or '',
            })
        
        data = {
            'success': True,
            'item_id': item.id,
            'item_name': item.item_name,
            'unit_price': float(item.unit_selling_price),
            'current_available': item.available_quantity,
            'total_required': total_required,
            'requirements_count': len(requirements_list),
            'requirements': requirements_list
        }
        
        return JsonResponse(data)
        
    except InventoryItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Inventory item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def inventory(request):
    """Display inventory items with enhanced tracking - FIXED VERSION"""
    items = InventoryItem.objects.all().order_by('item_name')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        items = items.filter(item_name__icontains=search_query)
    
    # Annotate with order requirements count
    from django.db.models import Count, Sum
    items = items.annotate(
        requirements_count=Count('order_requirements'),
        total_shortage=Sum('order_requirements__shortage_quantity')
    )
    
    # Calculate stats
    low_stock_count = items.filter(available_quantity__lt=10, available_quantity__gt=0).count()
    out_of_stock_count = items.filter(available_quantity=0).count()
    
    # Items with pending requirements
    items_with_requirements = items.filter(requirements_count__gt=0).count()
    
    context = {
        'items': items,
        'search_query': search_query,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'items_with_requirements': items_with_requirements,
    }
    
    return render(request, 'lms/inventory.html', context)
@login_required
@require_POST
def add_inventory_item(request):
    """Add a new inventory item"""
    try:
        item_name = request.POST.get('item_name', '').strip()
        unit_selling_price = request.POST.get('unit_selling_price', '').strip()
        available_quantity = request.POST.get('available_quantity', '0')
        quantity_to_be_ordered = request.POST.get('quantity_to_be_ordered', '0')
        
        if not item_name or not unit_selling_price:
            messages.error(request, 'Item name and price are required!')
            return redirect('inventory')
        
        item = InventoryItem.objects.create(
            item_name=item_name,
            unit_selling_price=unit_selling_price,
            available_quantity=int(available_quantity),
            quantity_to_be_ordered=int(quantity_to_be_ordered)
        )
        
        messages.success(request, f'Item "{item_name}" added successfully!')
        return redirect('inventory')
        
    except Exception as e:
        messages.error(request, f'Error adding item: {str(e)}')
        return redirect('inventory')


@login_required
@require_POST
def update_inventory_item(request, item_id):
    """Update inventory item quantities"""
    try:
        item = get_object_or_404(InventoryItem, id=item_id)
        
        available_quantity = request.POST.get('available_quantity')
        quantity_to_be_ordered = request.POST.get('quantity_to_be_ordered')
        
        if available_quantity:
            item.available_quantity = int(available_quantity)
        
        if quantity_to_be_ordered:
            item.quantity_to_be_ordered = int(quantity_to_be_ordered)
        
        item.save()
        
        messages.success(request, f'Item "{item.item_name}" updated successfully!')
        return redirect('inventory')
        
    except Exception as e:
        messages.error(request, f'Error updating item: {str(e)}')
        return redirect('inventory')


@login_required
def events(request):
    """Display calendar events"""
    events_list = Event.objects.filter(user=request.user).order_by('-start_datetime')
    
    context = {
        'events': events_list,
    }
    
    return render(request, 'lms/events.html', context)


@login_required
@require_POST
def add_event(request):
    """Add a new calendar event"""
    try:
        start_datetime = request.POST.get('start_datetime')
        end_datetime = request.POST.get('end_datetime', '')
        agenda = request.POST.get('agenda', '').strip()
        
        if not start_datetime:
            messages.error(request, 'Start date/time is required!')
            return redirect('events')
        
        event = Event.objects.create(
            start_datetime=start_datetime,
            end_datetime=end_datetime if end_datetime else None,
            agenda=agenda,
            user=request.user
        )
        
        messages.success(request, 'Event created successfully!')
        return redirect('events')
        
    except Exception as e:
        messages.error(request, f'Error creating event: {str(e)}')
        return redirect('events')


@login_required
def api_projects_summary(request):
    """API endpoint for projects summary statistics"""
    if request.user.is_superuser or request.user.groups.filter(name="admin").exists():
        projects = Project.objects.all()
    else:
        projects = Project.objects.filter(user=request.user)
    
    summary = {
        'total': projects.count(),
        'active': projects.filter(status__in=['In Progress', 'Testing']).count(),
        'completed': projects.filter(status='Completed').count(),
        'on_hold': projects.filter(status='On Hold').count(),
    }
    return JsonResponse(summary)

@login_required
@require_POST
def change_boq_status(request, boq_id):
    """Change BOQ status"""
    try:
        boq = get_object_or_404(BOQ, id=boq_id)
        new_status = request.POST.get('status')
        
        if new_status in dict(BOQ.STATUS_CHOICES):
            old_status = boq.status
            boq.status = new_status
            boq.save()
            
            # If approved, update lead status to advanced
            if new_status == 'approved' and boq.lead_source.status == 'boq':
                boq.lead_source.status = 'advanced'
                boq.lead_source.save()
            
            messages.success(request, f'BOQ status changed from {old_status} to {new_status}')
        else:
            messages.error(request, 'Invalid status!')
        
        return redirect('view_boq', boq_id=boq_id)
        
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
        return redirect('view_boq', boq_id=boq_id)


@login_required
@require_POST
def delete_boq(request, boq_id):
    """Delete a BOQ"""
    try:
        boq = get_object_or_404(BOQ, id=boq_id)
        lead_id = boq.lead_source.id
        
        # Check if user has permission
        if boq.status == 'approved':
            messages.error(request, 'Cannot delete approved BOQ!')
            return redirect('view_boq', boq_id=boq_id)
        
        # Check permissions
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if boq.created_by != request.user:
                messages.error(request, 'You do not have permission to delete this BOQ.')
                return redirect('view_boq', boq_id=boq_id)
        
        boq.delete()
        messages.success(request, 'BOQ deleted successfully!')
        return redirect('lead_detail', lead_id=lead_id)
        
    except Exception as e:
        messages.error(request, f'Error deleting BOQ: {str(e)}')
        return redirect('lead_detail', lead_id=lead_id)


@login_required
def inventory(request):
    """Display inventory items with enhanced tracking"""
    items = InventoryItem.objects.all().order_by('item_name')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        items = items.filter(item_name__icontains=search_query)
    
    # Calculate stats
    low_stock_count = items.filter(available_quantity__lt=10, available_quantity__gt=0).count()
    out_of_stock_count = items.filter(available_quantity=0).count()
    total_to_order = sum(item.quantity_to_be_ordered for item in items)
    
    context = {
        'items': items,
        'search_query': search_query,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_to_order': total_to_order,
    }
    
    return render(request, 'lms/inventory.html', context)


@login_required
def get_inventory_requirements(request, item_id):
    """API endpoint to get inventory requirements by project"""
    try:
        item = get_object_or_404(InventoryItem, id=item_id)
        requirements = InventoryOrderRequirement.objects.filter(
            inventory_item=item
        ).select_related('project', 'boq', 'boq_item')
        
        data = {
            'item_name': item.item_name,
            'total_required': sum(r.shortage_quantity for r in requirements),
            'requirements': [
                {
                    'project_name': req.project.project_name,
                    'boq_number': req.boq.invoice_number,
                    'required_qty': req.required_quantity,
                    'available_qty': req.available_quantity,
                    'shortage_qty': req.shortage_quantity,
                    'status': req.status,
                }
                for req in requirements
            ]
        }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def api_leads_summary(request):
    """API endpoint for leads summary statistics"""
    if request.user.is_superuser or request.user.groups.filter(name="admin").exists():
        leads = LeadSource.objects.all()
    else:
        leads = LeadSource.objects.filter(user=request.user)
    
    summary = {
        'total': leads.count(),
        'open': leads.filter(status='open').count(),
        'contacted': leads.filter(status='contacted').count(),
        'boq': leads.filter(status='boq').count(),
        'advanced': leads.filter(status='advanced').count(),
        'won': leads.filter(status='won').count(),
        'closed': leads.filter(status='closed').count(),
        'lost': leads.filter(status='lost').count(),
    }
    return JsonResponse(summary)
from django.db import models
from django.conf import settings

@login_required
@login_required
def dashboard(request):
    """Dynamic and filterable dashboard — with LeadSource filters and pie chart"""
    user = request.user

    # === FILTERS ===
    lead_filter = request.GET.get('lead', '')
    city_filter = request.GET.get('city', '')
    status_filter = request.GET.get('status', '')

    # === PROJECTS ===
    projects = Project.objects.select_related('lead_source')

    if not user.is_superuser and not user.groups.filter(name="admin").exists():
        projects = projects.filter(user=user)

    if lead_filter:
        projects = projects.filter(lead_source__id=lead_filter)
    if city_filter:
        projects = projects.filter(lead_source__city__iexact=city_filter)
    if status_filter:
        projects = projects.filter(status=status_filter)

    total_projects = projects.count()

    # === STATUS COUNTS ===
    raw_status_counts = dict(
        projects.values('status')
                .annotate(count=Count('status'))
                .values_list('status', 'count')
    )

    status_map = {
        'open': 'New',
        'contacted': 'Contacted',
        'boq': 'BOQ',
        'advanced': 'Advanced',
        'In Progress': 'In Progress',
        'Testing': 'Testing',
        'won': 'Won',
        'closed': 'Closed',
        'lost': 'Lost',
    }

    status_counts = {
        status_map.get(key, key): raw_status_counts.get(key, 0)
        for key in status_map.keys()
    }

    # === LEAD SOURCE DISTRIBUTION ===
    lead_source_counts = dict(
        projects.values('lead_source__first_name', 'lead_source__last_name')
                .annotate(count=Count('id'))
                .order_by('-count')
                .values_list('lead_source__first_name', 'count')
    )

    # === CITY DISTRIBUTION ===
    city_counts = dict(
        projects.values('lead_source__city')
                .annotate(count=Count('id'))
                .order_by('-count')
                .values_list('lead_source__city', 'count')
    )

    # === REVENUE & KPIs ===
    won_projects = projects.filter(status='won')
    total_revenue = won_projects.aggregate(total=Sum('amount'))['total'] or 0

    won_count = won_projects.count()
    avg_deal = (total_revenue / won_count) if won_count > 0 else 0
    win_rate = round((won_count / total_projects * 100), 1) if total_projects > 0 else 0
    conversion_rate = win_rate

    # === TOP LEADS ===
    top_leads = projects.filter(amount__gt=0).order_by('-amount')[:5]

    # === REVENUE TREND ===
    today = timezone.now().date()
    months, revenue_data = [], []

    for i in range(11, -1, -1):
        month_date = today - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        next_month = (month_start.replace(year=month_start.year + 1, month=1, day=1)
                      if month_start.month == 12
                      else month_start.replace(month=month_start.month + 1, day=1))
        month_end = next_month - timedelta(days=1)

        month_revenue = projects.filter(
            status='won',
            snapshot_d__date__gte=month_start,
            snapshot_d__date__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or 0

        months.append(month_start.strftime('%b'))
        revenue_data.append(float(month_revenue))

    # === FILTER OPTIONS ===
    all_leads = LeadSource.objects.all()
    all_cities = list(LeadSource.objects.exclude(city__isnull=True).values_list('city', flat=True).distinct())
    all_statuses = list(Project.objects.values_list('status', flat=True).distinct())

    context = {
        'total_billing': int(total_revenue),
        'conversion_rate': conversion_rate,
        'avg_deal': int(avg_deal),
        'win_rate': win_rate,
        'status_counts': json.dumps(status_counts),
        'lead_source_counts': json.dumps(lead_source_counts),
        'city_counts': json.dumps(city_counts),
        'top_leads': top_leads,
        'revenue_labels': json.dumps(months),
        'revenue_data': json.dumps(revenue_data),
        'all_leads': all_leads,
        'all_cities': all_cities,
        'all_statuses': all_statuses,
        'lead_filter': lead_filter,
        'city_filter': city_filter,
        'status_filter': status_filter,
    }
    print(lead_source_counts)


    return render(request, 'lms/dashboard.html', context)


# ============================================================================
# PROJECT VIEWS
# ============================================================================

@login_required
def ongoing_projects(request):
    projects = Project.objects.exclude(status='open').select_related('lead_source').order_by('-id')
    return render(request, 'lms/ongoing_projects.html', {'projects': projects})


from .models import Project, BOQ

def project_boq_detail(request, project_id):
    # Get project
    project = get_object_or_404(Project, id=project_id)

    # Get the linked lead source
    lead = project.lead_source

    # Get all BOQs for this project
    boqs = BOQ.objects.filter(project=project).order_by('-created_at')

    # Get inventory items for the "Add Item" section
    inventory_items = InventoryItem.objects.all()

    # Reuse the existing lead_detail.html template
    return render(request, 'lms/lead_detail.html', {
        'lead': lead,
        'boqs': boqs,
        'inventory_items': inventory_items,
        'project': project,  # optional context if needed
    })


@login_required
def project_detail(request, project_id):
    """Display detailed information about a specific project"""
    project = get_object_or_404(Project, id=project_id)
    tasks = Task.objects.filter(project=project).order_by('-due_date')
    invoices = Invoice.objects.filter(project=project).order_by('-snapshot_d')
    
    context = {
        'project': project,
        'tasks': tasks,
        'invoices': invoices,
    }
    
    return render(request, 'lms/project_detail.html', context)


@login_required
@require_POST
def add_project(request):
    """Add a new project"""
    try:
        project_name = request.POST.get('project_name', '').strip()
        amount = request.POST.get('amount', '').strip()
        expected_closure = request.POST.get('expected_closure', '').strip()
        status = request.POST.get('status', 'open')
        lead_source_id = request.POST.get('lead_source_id', '').strip()
        remarks = request.POST.get('remarks', '').strip()
        
        # Validation
        if not project_name or not lead_source_id:
            messages.error(request, 'Project name and lead source are required!')
            return redirect('leads')
        
        lead_source = get_object_or_404(LeadSource, id=lead_source_id)
        
        # Create project
        project = Project.objects.create(
            project_name=project_name,
            amount=amount if amount else None,
            expected_closure=expected_closure if expected_closure else None,
            status=status,
            lead_source=lead_source,
            remarks=remarks,
            user=request.user
        )
        
        messages.success(request, f'Project "{project_name}" created successfully!')
        referer = request.META.get('HTTP_REFERER')
        return HttpResponseRedirect(referer or reverse('ongoing_projects'))
        
    except Exception as e:
        messages.error(request, f'Error creating project: {str(e)}')
        referer = request.META.get('HTTP_REFERER')
        return HttpResponseRedirect(referer or reverse('ongoing_projects'))

# ============================================================================
# DASHBOARD (Chart.js)
# ============================================================================

@login_required
def tasks(request):
    user = request.user
    print(user)
    # Role-based filtering
    if user.groups.filter(name="admin").exists():
        tasks = Task.objects.all()
    else:
        tasks = Task.objects.filter(user=user)

    # Segregation logic
    active_tasks = [t for t in tasks if not t.completed and t.due_date > timezone.now()]
    completed_tasks = [t for t in tasks if t.completed]
    pending_tasks = [t for t in tasks if not t.completed and t.due_date <= timezone.now()]
    projects = Project.objects.all()
    users = User.objects.all()
    is_admin = request.user.groups.filter(name="admin").exists()
    notifications_qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications_qs.filter(is_read=False).count()
    notifications = notifications_qs[:5]


    context = {
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "projects": projects,
        "users": users,
        "is_admin": is_admin, 
        "notifications": notifications,
        "unread_count": unread_count
    }


    return render(request, "lms/tasks.html", context)


@login_required
@require_POST
def add_task(request):
    print(request)
    """Add a new task"""
    if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
        messages.error(request, 'You do not have permission to create tasks.')
        return redirect('tasks')
    
    try:
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date = request.POST.get('due_date', '').strip()
        project_id = request.POST.get('project', '').strip()
        user_id = request.POST.get('user', '').strip()
        priority = request.POST.get('priority')
        if not title or not project_id or not user_id:
            messages.error(request, 'Title, project and user are required!')
            return redirect('tasks')
        
        project = get_object_or_404(Project, id=project_id)
        user = get_object_or_404(get_user_model(), id=user_id)
        task = Task.objects.create(
            title=title,
            description=description,
            due_date=due_date if due_date else None,
            project=project,
            user=user,
            completed=False,
            priority=priority
        )
        
        # Create TaskAssignment to trigger notification
        TaskAssignment.objects.create(task=task, user=user)
        
        messages.success(request, f'Task "{title}" created successfully!')
        return redirect('tasks')
        
    except Exception as e:
        messages.error(request, f'Error creating task: {str(e)}')
        return redirect('tasks')

from django.contrib.auth.decorators import user_passes_test

def is_admin_or_superuser(user):
    return user.is_superuser or user.groups.filter(name='admin').exists()

@user_passes_test(is_admin_or_superuser)
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        task.title = request.POST.get('title')
        task.description = request.POST.get('description')
        task.due_date = request.POST.get('due_date')
        task.priority = request.POST.get('priority')
        task.save()
        messages.success(request, 'Task updated successfully!')
        return redirect('tasks')
    return render(request, 'lms/edit_task.html', {'task': task})

@user_passes_test(is_admin_or_superuser)
def delete_task(request, task_id):
    print('check')
    task = get_object_or_404(Task, id=task_id)
    task.delete()
    messages.success(request, 'Task deleted successfully!')
    return redirect('tasks')

@login_required
def get_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    return JsonResponse({
        "title": task.title,
        "description": task.description,
        "due_date": task.due_date.strftime("%Y-%m-%dT%H:%M") if task.due_date else "",
        "priority": task.priority,
    })

@login_required
@require_POST
def toggle_task(request, task_id):
    """Toggle task completion status"""
    try:
        task = get_object_or_404(Task, id=task_id)
        
        # Access control: Only superuser or assigned user can toggle
        if not request.user.is_superuser and task.user != request.user:
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to toggle this task!'
            }, status=403)
        
        task.completed = not task.completed
        task.save()
        
        status = "completed" if task.completed else "reopened"
        return JsonResponse({
            'success': True,
            'message': f'Task {status} successfully!',
            'completed': task.completed
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


# ============================================================================
# INVENTORY VIEWS
# ============================================================================

@login_required
def inventory(request):
    """Display inventory items"""
    items = InventoryItem.objects.all().order_by('item_name')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        items = items.filter(item_name__icontains=search_query)
    
    context = {
        'items': items,
        'search_query': search_query,
    }
    
    return render(request, 'lms/inventory.html', context)


@login_required
@require_POST
def add_inventory_item(request):
    """Add a new inventory item"""
    try:
        item_name = request.POST.get('item_name', '').strip()
        unit_selling_price = request.POST.get('unit_selling_price', '').strip()
        available_quantity = request.POST.get('available_quantity', '0')
        quantity_to_be_ordered = request.POST.get('quantity_to_be_ordered', '0')
        
        if not item_name or not unit_selling_price:
            messages.error(request, 'Item name and price are required!')
            return redirect('inventory')
        
        item = InventoryItem.objects.create(
            item_name=item_name,
            unit_selling_price=unit_selling_price,
            available_quantity=int(available_quantity),
            quantity_to_be_ordered=int(quantity_to_be_ordered)
        )
        
        messages.success(request, f'Item "{item_name}" added successfully!')
        return redirect('inventory')
        
    except Exception as e:
        messages.error(request, f'Error adding item: {str(e)}')
        return redirect('inventory')


# Replace or add these functions in your lms/views.py

@login_required
@require_POST
def add_inventory_item(request):
    """Add a new inventory item"""
    try:
        item_name = request.POST.get('item_name', '').strip()
        unit_selling_price = request.POST.get('unit_selling_price', '').strip()
        available_quantity = request.POST.get('available_quantity', '0')
        quantity_to_be_ordered = request.POST.get('quantity_to_be_ordered', '0')
        
        # Validation
        if not item_name or not unit_selling_price:
            messages.error(request, 'Item name and price are required!')
            return redirect('inventory')
        
        # Check for duplicate item name
        if InventoryItem.objects.filter(item_name__iexact=item_name).exists():
            messages.error(request, f'Item "{item_name}" already exists!')
            return redirect('inventory')
        
        # Create inventory item
        item = InventoryItem.objects.create(
            item_name=item_name,
            unit_selling_price=float(unit_selling_price),
            available_quantity=int(available_quantity),
            quantity_to_be_ordered=int(quantity_to_be_ordered)
        )
        
        messages.success(request, f'Item "{item_name}" added successfully!')
        return redirect('inventory')
        
    except ValueError as e:
        messages.error(request, 'Invalid number format!')
        return redirect('inventory')
    except Exception as e:
        messages.error(request, f'Error adding item: {str(e)}')
        return redirect('inventory')


@login_required
@require_POST
def update_inventory_item(request, item_id):
    """Update inventory item details"""
    try:
        item = get_object_or_404(InventoryItem, id=item_id)
        
        # Get form data
        item_name = request.POST.get('item_name', '').strip()
        unit_selling_price = request.POST.get('unit_selling_price', '').strip()
        available_quantity = request.POST.get('available_quantity')
        quantity_to_be_ordered = request.POST.get('quantity_to_be_ordered')
        add_quantity = request.POST.get('add_quantity')
        
        # Update item name if provided
        if item_name:
            # Check for duplicate name (excluding current item)
            if InventoryItem.objects.filter(item_name__iexact=item_name).exclude(id=item_id).exists():
                messages.error(request, f'Item "{item_name}" already exists!')
                return redirect('inventory')
            item.item_name = item_name
        
        # Update price if provided
        if unit_selling_price:
            item.unit_selling_price = float(unit_selling_price)
        
        # Handle stock addition (from "Add Stock" modal)
        if add_quantity:
            add_qty = int(add_quantity)
            item.available_quantity += add_qty
            messages.success(request, f'Added {add_qty} units to "{item.item_name}". New quantity: {item.available_quantity}')
        else:
            # Handle direct quantity update (from "Edit" modal)
            if available_quantity is not None:
                item.available_quantity = int(available_quantity)
            
            if quantity_to_be_ordered is not None:
                item.quantity_to_be_ordered = int(quantity_to_be_ordered)
            
            messages.success(request, f'Item "{item.item_name}" updated successfully!')
        
        item.save()
        return redirect('inventory')
        
    except ValueError as e:
        messages.error(request, 'Invalid number format!')
        return redirect('inventory')
    except Exception as e:
        messages.error(request, f'Error updating item: {str(e)}')
        return redirect('inventory')


@login_required
def inventory(request):
    """Display inventory items with enhanced tracking"""
    items = InventoryItem.objects.all().order_by('item_name')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        items = items.filter(item_name__icontains=search_query)
    
    # Calculate stats
    low_stock_count = items.filter(available_quantity__lt=10, available_quantity__gt=0).count()
    out_of_stock_count = items.filter(available_quantity=0).count()
    total_to_order = sum(item.quantity_to_be_ordered for item in items)
    
    context = {
        'items': items,
        'search_query': search_query,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_to_order': total_to_order,
    }
    
    return render(request, 'lms/inventory.html', context)

# ============================================================================
# EVENT/CALENDAR VIEWS
# ============================================================================

@login_required
def events(request):
    """Display calendar events"""
    events_list = Event.objects.filter(user=request.user).order_by('-start_datetime')
    
    context = {
        'events': events_list,
    }
    
    return render(request, 'lms/events.html', context)


@login_required
@require_POST
def add_event(request):
    """Add a new calendar event"""
    try:
        start_datetime = request.POST.get('start_datetime')
        end_datetime = request.POST.get('end_datetime', '')
        agenda = request.POST.get('agenda', '').strip()
        
        if not start_datetime:
            messages.error(request, 'Start date/time is required!')
            return redirect('events')
        
        event = Event.objects.create(
            start_datetime=start_datetime,
            end_datetime=end_datetime if end_datetime else None,
            agenda=agenda,
            user=request.user
        )
        
        messages.success(request, 'Event created successfully!')
        return redirect('events')
        
    except Exception as e:
        messages.error(request, f'Error creating event: {str(e)}')
        return redirect('events')


# ============================================================================
# API ENDPOINTS (for future AJAX functionality)
# ============================================================================

@login_required
def api_leads_summary(request):
    """API endpoint for leads summary statistics"""
    summary = {
        'total': LeadSource.objects.count(),
        'open': LeadSource.objects.filter(status='open').count(),
        'contacted': LeadSource.objects.filter(status='contacted').count(),
        'boq': LeadSource.objects.filter(status='boq').count(),
        'advanced': LeadSource.objects.filter(status='advanced').count(),
        'won': LeadSource.objects.filter(status='won').count(),
        'closed': LeadSource.objects.filter(status='closed').count(),
        'lost': LeadSource.objects.filter(status='lost').count(),
    }
    return JsonResponse(summary)


@login_required
def api_projects_summary(request):
    """API endpoint for projects summary statistics"""
    summary = {
        'total': Project.objects.count(),
        'active': Project.objects.filter(status__in=['open', 'contacted', 'boq', 'advanced']).count(),
        'won': Project.objects.filter(status='won').count(),
        'lost': Project.objects.filter(status='lost').count(),
    }
    return JsonResponse(summary)

# Add these functions to your lms/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from .models import Notification

@login_required
def notifications(request):
    """Display all notifications for the current user"""
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    
    context = {
        'notifications': notifications,
        'unread_count': unread_count,
        'is_admin': request.user.is_superuser or request.user.groups.filter(name="admin").exists(),
    }
    
    return render(request, 'lms/notifications.html', context)


@login_required
def mark_notifications_read(request):
    """Mark all notifications as read for the current user"""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, 'All notifications marked as read!')
    return redirect('notifications')


@login_required
@require_POST
def mark_notification_read(request, notif_id):
    """Mark a single notification as read"""
    try:
        notification = get_object_or_404(Notification, id=notif_id, user=request.user)
        notification.is_read = True
        notification.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Notification marked as read'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_POST
def delete_notification(request, notif_id):
    """Delete a notification"""
    try:
        notification = get_object_or_404(Notification, id=notif_id, user=request.user)
        notification.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Notification deleted'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
def unread_notification_count(request):
    """API endpoint for unread notification count"""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})

from .models import TaskAssignment, Notification

@login_required
@require_POST
def add_task_check(request):
    """Add a new task with notification"""
    try:
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date = request.POST.get('due_date', '').strip()
        project_id = request.POST.get('project_id', '').strip()
        user_id = request.POST.get('user_id', '').strip()
        
        if not title or not project_id or not user_id:
            messages.error(request, 'Title, project and user are required!')
            return redirect('tasks')
        
        project = get_object_or_404(Project, id=project_id)
        assigned_user = get_object_or_404(get_user_model(), id=user_id)
        
        # Create task
        task = Task.objects.create(
            title=title,
            description=description,
            due_date=due_date if due_date else None,
            project=project,
            user=assigned_user,
            completed=False
        )
        
        # Create TaskAssignment record (triggers notification signal)
        TaskAssignment.objects.create(
            task=task,
            user=assigned_user
        )
        
        messages.success(request, f'Task "{title}" assigned to {assigned_user.username} successfully!')
        return redirect('tasks')
        
    except Exception as e:
        messages.error(request, f'Error creating task: {str(e)}')
        return redirect('tasks')





@login_required
def unread_notification_count(request):
    """API endpoint for unread notification count"""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})

@csrf_exempt
def mark_task_complete(request, task_id):
    if request.method == 'POST':
        try:
            task = Task.objects.get(id=task_id)
            task.completed = True
            task.save()

            # Notify all admins
            channel_layer = get_channel_layer()
            admin_group = Group.objects.filter(name="admin").first()
            if admin_group:
                for admin in admin_group.user_set.all():
                    # DB notification
                    Notification.objects.create(
                        user=admin,
                        message=f"✅ Task '{task.title}' has been completed by {request.user.username}"
                    )

                    # Real-time WebSocket push
                    async_to_sync(channel_layer.group_send)(
                        f"user_{admin.id}",  # 👈 per admin WebSocket group
                        {
                            "type": "send_notification",
                            "message": f"✅ Task '{task.title}' completed by {request.user.username}"
                        }
                    )

            return JsonResponse({'status': 'success', 'message': 'Task marked complete'})
        except Task.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Task not found'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@csrf_exempt
def mark_task_incomplete(request, task_id):
    if request.method == 'POST':
        try:
            task = Task.objects.get(id=task_id)
            task.completed = False
            task.save()

            # Optional: send admin notification for reverting
            channel_layer = get_channel_layer()
            admin_group = Group.objects.filter(name="admin").first()
            if admin_group:
                for admin in admin_group.user_set.all():
                    Notification.objects.create(
                        user=admin,
                        message=f"❌ Task '{task.title}' was marked incomplete by {request.user.username}"
                    )

                    async_to_sync(channel_layer.group_send)(
                        f"user_{admin.id}",
                        {
                            "type": "send_notification",
                            "message": f"❌ Task '{task.title}' marked incomplete by {request.user.username}"
                        }
                    )

            return JsonResponse({'status': 'success', 'message': 'Task marked incomplete'})
        except Task.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Task not found'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})
