"""
Epic views for WoS backlog application.

Handles CRUD operations for epics:
- overview: List all epics with scores and CRUD actions
- create_epic: Create a new epic via dedicated page
- edit_epic: Edit an existing epic via dedicated page
"""
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Epic, Story


def overview(request):
    """Overview page showing all epics with aggregated scores.
    
    Handles POST actions:
    - create_epic: Create a new epic
    - edit_epic: Edit an existing epic
    - delete_epic: Delete an epic
    - archive_epic: Archive an epic and its stories
    - unarchive_epic: Unarchive an epic (stories remain archived)
    
    Supports filtering by archived status via ?archived=1 query param.
    """
    # Handle POST actions
    if request.method == 'POST':
        action = request.POST.get('action')
        epic_id = request.POST.get('epic_id')
        
        if action == 'create_epic':
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            if title:
                Epic.objects.create(title=title, description=description)
            return redirect(request.get_full_path())
        
        if action == 'edit_epic' and epic_id:
            epic = get_object_or_404(Epic, pk=epic_id)
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            if title:
                epic.title = title
                epic.description = description
                epic.save()
            return redirect(request.get_full_path())
        
        if action == 'delete_epic' and epic_id:
            epic = get_object_or_404(Epic, pk=epic_id)
            epic.delete()
            return redirect(request.get_full_path())
        
        if action == 'archive_epic' and epic_id:
            epic = get_object_or_404(Epic, pk=epic_id)
            epic.archived = True
            epic.save()
            # Cascade archive to all stories in this epic
            epic.stories.update(archived=True)
            return redirect(request.get_full_path())
        
        if action == 'unarchive_epic' and epic_id:
            epic = get_object_or_404(Epic, pk=epic_id)
            epic.archived = False
            epic.save()
            # Note: Stories remain archived - user must manually unarchive them
            return redirect(request.get_full_path())
    
    # Filter by archived status
    show_archived = request.GET.get('archived', '') == '1'
    epics_qs = Epic.objects.filter(archived=show_archived).prefetch_related('stories').order_by('title')
    
    # Build epics data with unfinished_count for archive confirmation
    epics_data = []
    for epic in epics_qs:
        # Count unfinished, non-archived stories
        unfinished_count = epic.stories.filter(archived=False, finished__isnull=True).count()
        epics_data.append({
            'epic': epic,
            'unfinished_count': unfinished_count,
        })
    
    context = {
        'epics': epics_data,
        'show_archived': show_archived,
    }
    return render(request, 'backlog/overview.html', context)


def create_epic(request):
    """Create a new Epic via dedicated form page.
    
    GET: Display the creation form
    POST: Create epic and redirect to overview
    """
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            Epic.objects.create(title=title, description=description)
            return redirect('backlog:epics')
    return render(request, 'backlog/create_epic.html', {})


def edit_epic(request, pk):
    """Edit an existing Epic.
    
    GET: Display edit form with current values
    POST: Update epic and redirect to overview
    """
    epic = get_object_or_404(Epic, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            epic.title = title
            epic.description = description
            epic.save()
            return redirect('backlog:epics')
        # fall through and show form with current values
    return render(request, 'backlog/edit_epic.html', {'epic': epic})
