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
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import redirect
from .models import InventoryItem
from functools import wraps

def has_group(user, group_name):
    """Check if a user belongs to a specific group."""
    return user.is_authenticated and user.groups.filter(name=group_name).exists()

def require_permission(*group_names):
    """
    Custom decorator that checks if user has any of the specified groups or is admin/superuser.
    Redirects to dashboard with error message if permission denied (instead of login page).
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Check if user is authenticated first
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Check if user is superuser or admin
            if request.user.is_superuser or request.user.groups.filter(name='admin').exists():
                return view_func(request, *args, **kwargs)
            
            # Check for any of the required groups
            for group_name in group_names:
                if request.user.groups.filter(name=group_name).exists():
                    return view_func(request, *args, **kwargs)
            
            # Permission denied - redirect to dashboard or referer with error message
            messages.error(request, 'You do not have permission to access this page.')
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return HttpResponseRedirect(referer)
            return redirect('dashboard')
        return wrapper
    return decorator

@login_required
@require_permission('admin')
def access_control(request):
    """Admin page to view and assign groups to users."""
    users = User.objects.exclude(is_superuser=True).select_related()
    groups = Group.objects.all().order_by('name')
    return render(request, 'lms/access_control.html', {'users': users, 'groups': groups})


@login_required
@require_permission('admin')
def update_user_groups(request):
    """Handle AJAX updates for assigning/removing groups."""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        group_name = request.POST.get('group_name')
        action = request.POST.get('action')

        try:
            user = User.objects.get(id=user_id)
            group = Group.objects.get(name=group_name)

            if action == 'add':
                user.groups.add(group)
            elif action == 'remove':
                user.groups.remove(group)

            return JsonResponse({'success': True, 'message': 'Updated successfully.'})
        except (User.DoesNotExist, Group.DoesNotExist):
            return JsonResponse({'success': False, 'message': 'User or group not found.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

@csrf_exempt
def add_inline_lead(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        country_code = data.get('country_code', '+91')
        phone_number = data.get('phone_number')
        address = data.get('address')

        if not first_name or not phone_number:
            return JsonResponse({'success': False, 'message': 'First name and phone number are required!'})

        # Create lead
        lead = LeadSource.objects.create(
            first_name=first_name,
            last_name=last_name,
            country_code=country_code,
            phone_number=phone_number,
            address=address,
            user=request.user 

        )

        return JsonResponse({
            'success': True,
            'message': 'Lead created successfully',
            'id': lead.id,
            'first_name': lead.first_name,
            'last_name': lead.last_name,
        })
@login_required
@require_POST
def update_project_status(request, project_id):
    """Update project status via AJAX"""
    try:
        project = get_object_or_404(Project, id=project_id)
        new_status = request.POST.get('status')
        
        # Access control
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if project.user != request.user:
                return JsonResponse({
                    'success': False,
                    'message': 'You do not have permission to update this project!'
                }, status=403)
        
        # Validate status
        valid_statuses = ['open', 'contacted', 'boq', 'advanced', 'In Progress', 'won', 'closed', 'lost']
        if new_status not in valid_statuses:
            return JsonResponse({
                'success': False,
                'message': 'Invalid status value!'
            }, status=400)
        
        old_status = project.status
        project.status = new_status
        project.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Status updated from {old_status} to {new_status} successfully!'
        })
        
    except Project.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Project not found!'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)
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

    data = list(leads.values('id', 'first_name', 'last_name'))
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
            return redirect('dashboard')
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
@require_permission('leads_access')
def leads_list(request):
    """Display list of all leads with search and filter capabilities"""

    if request.user.is_superuser or request.user.groups.filter(name="admin").exists():
        leads = LeadSource.objects.all().order_by('-snapshot_d')
        projects = Project.objects.select_related('lead_source').all()
    else:
        leads = LeadSource.objects.all().order_by('-snapshot_d')
        projects = Project.objects.select_related('lead_source').all()
    
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
        projects = projects.filter(city=city_filter)
    
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
            project_name = f"{lead.first_name} {lead.last_name} "
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
def lead_detail(request, project_id):
    """Display detailed information about a lead using project_id"""
    project = get_object_or_404(Project, id=project_id)
    lead = project.lead_source
    
    # All projects for this lead (optional, keeps your UI same)
    projects = Project.objects.filter(lead_source=lead).order_by('-snapshot_d')
    
    context = {
        'lead': lead,
        'project': project,
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
def lead_detail(request, project_id):
    """Display detailed information about a specific project and its lead with BOQ functionality"""
    
    # Get project first
    project = get_object_or_404(Project, id=project_id)
    
    # Get the lead linked to this project
    lead = project.lead_source

    # Permission check
    if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
        if lead.user != request.user:
            messages.error(request, 'You do not have permission to view this project.')
            return redirect('ongoing_projects')

    # All projects for same lead
    projects = Project.objects.filter(lead_source=lead).order_by('-snapshot_d')
    
    # BOQs linked to the project (NOT to lead)
    boqs = BOQ.objects.filter(project=project).order_by('-created_at')

    # Inventory
    inventory_items = InventoryItem.objects.all().order_by('item_name')

    return render(request, 'lms/lead_detail.html', {
        'lead': lead,
        'project': project,
        'projects': projects,
        'boqs': boqs,
        'inventory_items': inventory_items,
    })



@login_required
@require_POST
def create_boq(request, project_id):
    """Create BOQ from project screen"""
    from decimal import Decimal
    from django.db.models import F

    project = get_object_or_404(Project, id=project_id)
    lead = project.lead_source  # required for invoice numbering

    # Get BOQ form inputs
    tax_rate = Decimal(request.POST.get('tax_rate', '18.00'))
    overall_discount_percentage = Decimal(request.POST.get('overall_discount_percentage', '0'))
    notes = request.POST.get('notes', '')

    # Create BOQ
    boq = BOQ.objects.create(
        lead_source=lead,
        project=project,
        tax_rate=tax_rate,
        overall_discount_percentage=overall_discount_percentage,
        notes=notes,
        created_by=request.user
    )

    # Get items arrays
    sr_nos = request.POST.getlist('sr_no[]')
    inventory_ids = request.POST.getlist('inventory_id[]')
    quantities = request.POST.getlist('quantity[]')
    discounts = request.POST.getlist('discount[]')

    valid_items = [
        i for i, inv_id in enumerate(inventory_ids)
        if inv_id and inv_id.strip()
    ]

    if not valid_items:
        boq.delete()
        messages.error(request, "Please add at least 1 item in the BOQ.")
        return redirect("project_boq_detail", project_id=project_id)

    items_created = 0

    for i in valid_items:
        try:
            inventory = get_object_or_404(InventoryItem, id=int(inventory_ids[i]))
            quantity = int(quantities[i])
            discount = Decimal(discounts[i]) if discounts[i] else Decimal('0')

            boq_item = BOQItem.objects.create(
                boq=boq,
                sr_no=int(sr_nos[i]),
                inventory_item=inventory,
                quantity=quantity,
                discount_percentage=discount
            )

            items_created += 1

            # 🔥 Reduce inventory stock safely
            inventory.available_quantity = F('available_quantity') - quantity
            inventory.save()

            # If stock not sufficient → create order requirement
            if not boq_item.has_sufficient_stock:
                shortage = boq_item.quantity - boq_item.available_quantity

                InventoryOrderRequirement.objects.create(
                    inventory_item=inventory,
                    project=project,
                    boq=boq,
                    boq_item=boq_item,
                    required_quantity=quantity,
                    available_quantity=boq_item.available_quantity,
                    shortage_quantity=shortage,
                    status='pending'
                )

        except Exception as e:
            messages.warning(request, f"Error adding BOQ item {i+1}: {str(e)}")
            continue

    if items_created == 0:
        boq.delete()
        messages.error(request, "No BOQ items could be saved!")
        return redirect("project_boq_detail", project_id=project_id)

    # Calculate totals
    boq.calculate_totals()
    boq.refresh_from_db()

    # Update project amount with BOQ total
    project.amount = boq.grand_total
    project.save()

    messages.success(request, f"BOQ {boq.invoice_number} created successfully!")
    return redirect("view_boq", boq_id=boq.id)

@login_required
@require_permission('project_permission_edit')
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
            city = request.POST.get('city', '').strip()

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
            project.city = city
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
@require_permission('inventory_access_view')
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
    total_to_order = sum(item.quantity_to_be_ordered for item in items)
    
    context = {
        'items': items,
        'search_query': search_query,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_to_order': total_to_order,
    }
    
    return render(request, 'lms/inventory.html', context)

# Add this function to your lms/views.py file
# Place it near your other inventory-related functions

@login_required
@require_permission('inventory_access_edit')
@require_POST
def upload_inventory_excel(request):
    """Upload inventory items from Excel file"""
    try:
        if 'excel_file' not in request.FILES:
            messages.error(request, 'No file uploaded!')
            return redirect('inventory')
        
        excel_file = request.FILES['excel_file']
        
        # Validate file extension
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, 'Invalid file format! Please upload an Excel file (.xlsx or .xls)')
            return redirect('inventory')
        
        # Read Excel file
        try:
            import openpyxl
            wb = openpyxl.load_workbook(excel_file)
            ws = wb.active
        except Exception as e:
            messages.error(request, f'Error reading Excel file: {str(e)}')
            return redirect('inventory')
        
        # Process rows (skip header)
        added_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                # Expected columns: Item Name, Unit Selling Price, Available Quantity, Quantity to be Ordered
                if not row or not row[0]:  # Skip empty rows
                    continue
                
                item_name = str(row[0]).strip()
                unit_selling_price = float(row[1]) if row[1] else 0
                available_quantity = int(row[2]) if row[2] else 0
                quantity_to_be_ordered = int(row[3]) if len(row) > 3 and row[3] else 0
                
                # Validation
                if not item_name:
                    errors.append(f'Row {row_num}: Item name is required')
                    error_count += 1
                    continue
                
                if unit_selling_price <= 0:
                    errors.append(f'Row {row_num}: Unit price must be greater than 0')
                    error_count += 1
                    continue
                
                # Check if item exists
                existing_item = InventoryItem.objects.filter(item_name__iexact=item_name).first()
                
                if existing_item:
                    # Update existing item (add to existing quantities)
                    existing_item.available_quantity += available_quantity
                    if quantity_to_be_ordered > 0:
                        existing_item.quantity_to_be_ordered += quantity_to_be_ordered
                    existing_item.unit_selling_price = unit_selling_price  # Update price
                    existing_item.save()
                    updated_count += 1
                else:
                    # Create new item
                    InventoryItem.objects.create(
                        item_name=item_name,
                        unit_selling_price=unit_selling_price,
                        available_quantity=available_quantity,
                        quantity_to_be_ordered=quantity_to_be_ordered
                    )
                    added_count += 1
                
            except Exception as e:
                errors.append(f'Row {row_num}: {str(e)}')
                error_count += 1
                continue
        
        # Success message
        if added_count > 0 or updated_count > 0:
            messages.success(request, 
                f'Excel upload completed! Added: {added_count}, Updated: {updated_count}, Errors: {error_count}')
        
        # Show errors if any
        if errors:
            error_message = '<br>'.join(errors[:10])  # Show first 10 errors
            if len(errors) > 10:
                error_message += f'<br>... and {len(errors) - 10} more errors'
            from django.utils.safestring import mark_safe
            messages.warning(request, mark_safe(f'Some rows had errors:<br>{error_message}'))
        
        return redirect('inventory')
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f'Error processing Excel file: {str(e)}')
        return redirect('inventory')

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
@require_permission('basic_access')
def dashboard(request):
    """Dynamic and filterable dashboard with inventory and city-wise sales"""
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
        projects = projects.filter(city=city_filter)
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
                .order_by('-count')[:8]
                .values_list('lead_source__first_name', 'count')
    )

    # === CITY DISTRIBUTION ===

    city_counts = dict(
        projects.exclude(city__isnull=True)
                .values('city')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
                .values_list('city', 'count')
    )

    # === REVENUE & KPIs (FIXED) ===
    # Calculate total revenue from ALL projects with amount > 0
    projects_with_amount = projects.exclude(amount__isnull=True).exclude(amount=0)
    total_revenue = projects_with_amount.aggregate(total=Sum('amount'))['total'] or 0
    
    # Count won projects for win rate
    won_projects = projects.filter(status='won')
    won_count = won_projects.count()
    
    # Calculate average deal size from projects with amounts
    total_projects_with_amount = projects_with_amount.count()
    avg_deal = (total_revenue / total_projects_with_amount) if total_projects_with_amount > 0 else 0
    
    # Win rate = won projects / total projects
    win_rate = round((won_count / total_projects * 100), 1) if total_projects > 0 else 0
    
    # Conversion rate: projects with amount / total projects
    conversion_rate = round((total_projects_with_amount / total_projects * 100), 1) if total_projects > 0 else 0

    # === TOP PROJECTS ===
    top_leads = projects.filter(amount__gt=0).order_by('-amount')[:10]

    # === TOP SELLING INVENTORY ===
    from django.db.models import F
    
    top_inventory = (
        BOQItem.objects
        .filter(boq__status='approved')
        .values('inventory_item__id', 'inventory_item__item_name')
        .annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('unit_price'))
        )
        .order_by('-total_revenue')[:10]
    )

    # Format inventory data
    top_inventory_list = [
        {
            'item_name': item['inventory_item__item_name'],
            'total_sold': item['total_sold'],
            'total_revenue': item['total_revenue']
        }
        for item in top_inventory
    ]

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
            amount__isnull=False,
            amount__gt=0,
            snapshot_d__date__gte=month_start,
            snapshot_d__date__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or 0

        months.append(month_start.strftime('%b'))
        revenue_data.append(float(month_revenue))

    # === FILTER OPTIONS ===
    all_leads = LeadSource.objects.all().order_by('first_name')
    all_cities = list(
        Project.objects.exclude(city__isnull=True)
        .exclude(city__exact="")
        .values_list('city', flat=True)
        .distinct()
        .order_by('city')
    )
    all_statuses = list(
        Project.objects.values_list('status', flat=True)
        .distinct()
        .order_by('status')
    )

    context = {
        'total_billing': int(total_revenue),
        'conversion_rate': conversion_rate,
        'avg_deal': int(avg_deal),
        'win_rate': win_rate,
        'status_counts': json.dumps(status_counts),
        'lead_source_counts': json.dumps(lead_source_counts),
        'city_counts': json.dumps(city_counts),
        'top_leads': top_leads,
        'top_inventory': top_inventory_list,
        'revenue_labels': json.dumps(months),
        'revenue_data': json.dumps(revenue_data),
        'all_leads': all_leads,
        'all_cities': all_cities,
        'all_statuses': all_statuses,
        'lead_filter': lead_filter,
        'city_filter': city_filter,
        'status_filter': status_filter,
    }

    return render(request, 'lms/dashboard.html', context)

@login_required
@require_POST
def update_project_amount(request, project_id):
    """Update project amount inline - syncs with lead"""
    from decimal import Decimal, InvalidOperation
    
    try:
        project = get_object_or_404(Project, id=project_id)
        
        # Access control
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if project.user != request.user:
                return JsonResponse({
                    'success': False,
                    'message': 'You do not have permission to update this project!'
                }, status=403)
        
        new_amount = request.POST.get('amount')
        
        if not new_amount:
            return JsonResponse({
                'success': False,
                'message': 'Amount is required!'
            }, status=400)
        
        try:
            new_amount = Decimal(new_amount)
            if new_amount < 0:
                return JsonResponse({
                    'success': False,
                    'message': 'Amount cannot be negative!'
                }, status=400)
        except (ValueError, InvalidOperation):
            return JsonResponse({
                'success': False,
                'message': 'Invalid amount format!'
            }, status=400)
        
        # Update project amount
        old_amount = project.amount
        project.amount = new_amount
        project.save()
        
        # Also update the latest BOQ's grand total if exists
        latest_boq = BOQ.objects.filter(project=project).order_by('-created_at').first()
        if latest_boq:
            # Recalculate BOQ totals based on items
            latest_boq.calculate_totals()
        
        return JsonResponse({
            'success': True,
            'message': f'Amount updated from ₹{old_amount} to ₹{new_amount}',
            'new_amount': float(new_amount)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

@login_required
@require_permission('inventory_access_edit')
@require_POST
def delete_inventory_item(request, item_id):
    """
    Soft-delete (or hard-delete) an inventory item.
    Only users with edit permission can do it.
    """
    try:
        item = get_object_or_404(InventoryItem, id=item_id)

        # OPTIONAL: protect items that are already used in BOQs
        if BOQItem.objects.filter(inventory_item=item).exists():
            messages.error(request,
                f'Cannot delete “{item.item_name}” – it is used in one or more BOQs.')
            return redirect('inventory')

        item_name = item.item_name
        item.delete()
        messages.success(request, f'Item “{item_name}” deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting item: {str(e)}')
    return redirect('inventory')


# ============================================================================
# PROJECT VIEWS
# ============================================================================

@login_required
@require_permission('ongoing_projects_access')
def ongoing_projects(request):
    projects = Project.objects.exclude(status__in=['open', 'contacted','won','In Progress']).select_related('lead_source').order_by('-id')
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
def update_invoice_number(request, boq_id):
    boq = get_object_or_404(BOQ, id=boq_id)
    new_invoice = request.POST.get("invoice_number", "").strip()

    if not new_invoice:
        messages.error(request, "Invoice number cannot be empty.")
        return redirect("view_boq", boq_id=boq_id)

    if BOQ.objects.filter(invoice_number=new_invoice).exclude(id=boq_id).exists():
        messages.error(request, "Invoice number already exists.")
        return redirect("view_boq", boq_id=boq_id)

    boq.invoice_number = new_invoice
    boq.save()

    messages.success(request, "Invoice number updated successfully!")
    return redirect("view_boq", boq_id=boq_id)

@login_required
@require_POST
@require_permission('project_permission_edit')
def add_project(request):
    """Add a new project"""
    try:
        project_name = request.POST.get('project_name', '').strip()
        amount = request.POST.get('amount', '').strip()
        expected_closure = request.POST.get('expected_closure', '').strip()
        status = request.POST.get('status', 'open')
        lead_source_id = request.POST.get('lead_source_id', '').strip()
        remarks = request.POST.get('remarks', '').strip()
        city = request.POST.get('city', '').strip()
        
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
            user=request.user,
            city=city
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
@require_permission('basic_access')
def tasks(request):
    user = request.user
    # Build two views: Assigned to Me and Assigned by Me
    assigned_to_qs = Task.objects.filter(user=user)
    assigned_by_qs = Task.objects.filter(assigned_by=user)
    now = timezone.now()
    # Segregation logic for both views
    assigned_to_active_tasks = [t for t in assigned_to_qs if not t.completed and t.due_date > now]
    assigned_to_completed_tasks = [t for t in assigned_to_qs if t.completed]
    assigned_to_pending_tasks = [t for t in assigned_to_qs if not t.completed and t.due_date <= now]
    assigned_by_active_tasks = [t for t in assigned_by_qs if not t.completed and t.due_date > now]
    assigned_by_completed_tasks = [t for t in assigned_by_qs if t.completed]
    assigned_by_pending_tasks = [t for t in assigned_by_qs if not t.completed and t.due_date <= now]
    # Counters for dynamic display
    assigned_to_active_count = len(assigned_to_active_tasks)
    assigned_to_completed_count = len(assigned_to_completed_tasks)
    assigned_to_pending_count = len(assigned_to_pending_tasks)
    assigned_by_active_count = len(assigned_by_active_tasks)
    assigned_by_completed_count = len(assigned_by_completed_tasks)
    assigned_by_pending_count = len(assigned_by_pending_tasks)
    projects = Project.objects.all()
    users = User.objects.all()
    is_admin = request.user.groups.filter(name="admin").exists()
    is_task_role = request.user.groups.filter(name="task_permission_edit").exists()
    notifications_qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications_qs.filter(is_read=False).count()
    notifications = notifications_qs[:5]

    context = {
        # Default view: Assigned to Me
        "active_tasks": assigned_to_active_tasks,
        "completed_tasks": assigned_to_completed_tasks,
        "pending_tasks": assigned_to_pending_tasks,
        # Full data sets for both views
        "assigned_to_active_tasks": assigned_to_active_tasks,
        "assigned_to_completed_tasks": assigned_to_completed_tasks,
        "assigned_to_pending_tasks": assigned_to_pending_tasks,
        "assigned_by_active_tasks": assigned_by_active_tasks,
        "assigned_by_completed_tasks": assigned_by_completed_tasks,
        "assigned_by_pending_tasks": assigned_by_pending_tasks,
        # Counters
        "assigned_to_active_count": assigned_to_active_count,
        "assigned_to_completed_count": assigned_to_completed_count,
        "assigned_to_pending_count": assigned_to_pending_count,
        "assigned_by_active_count": assigned_by_active_count,
        "assigned_by_completed_count": assigned_by_completed_count,
        "assigned_by_pending_count": assigned_by_pending_count,
        # Other context
        "projects": projects,
        "users": users,
        "is_admin": is_admin, 
        "notifications": notifications,
        "unread_count": unread_count,
        "is_task_role": is_task_role
    }

    return render(request, "lms/tasks.html", context)


@login_required
@require_POST
@require_permission('task_permission_edit')
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
            assigned_by=request.user,
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

@login_required
@require_permission('admin')
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

@login_required
@require_permission('task_permission_edit')
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




# Replace or add these functions in your lms/views.py

@login_required
@require_POST
@require_permission('inventory_access_edit')
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
@require_permission('inventory_access_edit')
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
                other_admins = admin_group.user_set.exclude(id=request.user.id)
                for admin in other_admins:
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
