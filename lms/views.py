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
    else:
        leads = LeadSource.objects.filter(user=request.user).order_by('-snapshot_d')
    
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

from django.db import models
from django.conf import settings

@login_required
def dashboard(request):
    """FULLY DYNAMIC DASHBOARD - NO HARDCODED DATA"""
    
    user = request.user
    
    # === 1. LEADS ===
    leads = LeadSource.objects.all() if user.is_superuser else LeadSource.objects.filter(user=user)
    total_leads = leads.count()

    # Get actual status counts safely
    raw_status_counts = dict(
        leads.values('status')
             .annotate(count=Count('status'))
             .values_list('status', 'count')
    )

    # Map internal status → display name
    status_map = {
        'open': 'New',
        'contacted': 'Contacted',
        'boq': 'BOQ',
        'advanced': 'Advanced',
        'won': 'Won',
        'closed': 'Closed',
        'lost': 'Lost',
    }

    # Build final status counts (default 0 if missing)
    status_counts = {
        status_map.get(key, key): raw_status_counts.get(key, 0)
        for key in status_map.keys()
    }

    # === 2. PROJECTS & REVENUE ===
    projects = Project.objects.select_related('lead_source').all() if user.is_superuser else Project.objects.select_related('lead_source').filter(user=user)
    total_projects = projects.count()

    won_projects = projects.filter(lead_source__status='won')
    total_revenue = won_projects.aggregate(total=Sum('amount'))['total'] or 0
    
    # Calculate average deal size
    won_count = won_projects.count()
    avg_deal = (total_revenue / won_count) if won_count > 0 else 0
    
    # Calculate win rate
    win_rate = round((won_count / total_leads * 100), 1) if total_leads > 0 else 0
    
    # Calculate conversion rate
    conversion_rate = round((raw_status_counts.get('won', 0) / total_leads * 100), 1) if total_leads > 0 else 0

    # === 3. TOP LEADS (by project amount) ===
    top_leads = Project.objects.select_related('lead_source') \
        .filter(amount__isnull=False, amount__gt=0) \
        .order_by('-amount')[:5]

    # === 4. REVENUE TREND (Last 12 months) ===
    today = timezone.now().date()
    months = []
    revenue_data = []

    for i in range(11, -1, -1):
        month_date = today - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        
        # Calculate end of month
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1, day=1)
        month_end = next_month - timedelta(days=1)

        # Get revenue for won projects in this month
        month_revenue = Project.objects.filter(
            lead_source__status='won',
            snapshot_d__date__gte=month_start,
            snapshot_d__date__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or 0

        months.append(month_date.strftime('%b'))
        revenue_data.append(float(month_revenue))

    # === CONTEXT ===
    context = {
        'total_billing': int(total_revenue),
        'conversion_rate': conversion_rate,
        'avg_deal': int(avg_deal),
        'win_rate': win_rate,
        'status_counts': status_counts,
        'top_leads': top_leads,
        'revenue_labels': months,
        'revenue_data': revenue_data,
    }

    return render(request, 'lms/dashboard.html', context)

# ============================================================================
# PROJECT VIEWS
# ============================================================================

@login_required
def ongoing_projects(request):
    """Display list of ongoing projects"""
    q_objects = Q(lead_source__status__in=['advanced', 'won']) | Q(status__in=['In Progress', 'Testing', 'On Hold'])
    if request.user.is_superuser:
        projects = Project.objects.filter(q_objects).select_related('lead_source', 'user').distinct().order_by('-snapshot_d')
    else:
        projects = Project.objects.filter(user=request.user).filter(q_objects).select_related('lead_source', 'user').distinct().order_by('-snapshot_d')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        projects = projects.filter(
            Q(project_name__icontains=search_query) |
            Q(lead_source__first_name__icontains=search_query) |
            Q(lead_source__last_name__icontains=search_query)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        projects = projects.filter(status=status_filter)
    
    context = {
        'projects': projects,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    
    return render(request, 'lms/ongoing_projects.html', context)


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
            return redirect('ongoing_projects')
        
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
        return redirect('ongoing_projects')
        
    except Exception as e:
        messages.error(request, f'Error creating project: {str(e)}')
        return redirect('ongoing_projects')

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


@login_required
def notifications(request):
    """Display all notifications for the current user"""
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'notifications': notifications,
    }
    
    return render(request, 'lms/notifications.html', context)

# Add this to your views.py
@login_required
def mark_notifications_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, 'All notifications marked as read!')
    return redirect('notifications')

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
