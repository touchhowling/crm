from django.shortcuts import render
from .models import LeadSource

def leads_list(request):
    leads = LeadSource.objects.all().order_by('-snapshot_d')
    return render(request, 'lms/leads_list.html', {'leads': leads})
def dashboard(request):
    return render(request, 'lms/dashboard.html')
def ongoing_projects(request):
    return render(request, 'lms/ongoing_projects.html')
def tasks(request): 
    return render(request, 'lms/tasks.html')
def inventory(request):
    return render(request, 'lms/inventory.html')
