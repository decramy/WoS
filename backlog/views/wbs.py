"""
Work Breakdown Structure (WBS) views for WoS backlog application.

Provides visual dependency mapping:
- wbs_view: Main WBS grid with Gantt-style bars
- wbs_add_dependency: AJAX endpoint to add dependencies
- wbs_remove_dependency: AJAX endpoint to remove dependencies
"""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import Epic, Story, StoryDependency


def wbs_view(request):
    """Work Breakdown Structure showing stories with dependencies.
    
    Displays:
    - Stories grouped by epic in a grid layout
    - Dependency relationships between stories
    - Gantt-style bars showing relative cost/effort
    
    Supports filtering by epic and AJAX dependency management.
    """
    epic_id = request.GET.get('epic', '')
    all_epics = Epic.objects.filter(archived=False).order_by('title')
    
    # Get stories based on filter (exclude archived)
    if epic_id:
        stories_qs = Story.objects.filter(epic_id=epic_id, archived=False).select_related('epic').prefetch_related(
            'dependencies__depends_on', 'dependents__story', 'cost_scores__answer'
        )
    else:
        stories_qs = Story.objects.filter(archived=False).select_related('epic').prefetch_related(
            'dependencies__depends_on', 'dependents__story', 'cost_scores__answer'
        )
    
    stories_qs = stories_qs.order_by('epic__title', 'title')
    
    # Calculate max cost for scaling the Gantt bars
    max_cost = 1  # minimum to avoid division by zero
    story_costs = {}
    for story in stories_qs:
        cost_sum = sum(cs.answer.score for cs in story.cost_scores.all() if cs.answer)
        story_costs[story.id] = cost_sum
        if cost_sum > max_cost:
            max_cost = cost_sum
    
    # Build story data with positions for the visual layout
    stories_data = []
    dependencies_data = []
    gantt_data = []  # For the Gantt chart
    
    # Group stories by epic for layout
    epics_with_stories = {}
    for story in stories_qs:
        epic_title = story.epic.title
        if epic_title not in epics_with_stories:
            epics_with_stories[epic_title] = []
        epics_with_stories[epic_title].append(story)
    
    # Assign positions - grid layout by epic
    story_positions = {}
    col = 0
    for epic_title, epic_stories in epics_with_stories.items():
        for row, story in enumerate(epic_stories):
            story_positions[story.id] = {'col': col, 'row': row}
            cost = story_costs.get(story.id, 0)
            cost_percent = (cost / max_cost * 100) if max_cost > 0 else 0
            
            story_entry = {
                'id': story.id,
                'title': story.title,
                'epic_id': story.epic.id,
                'epic_title': epic_title,
                'status': story.computed_status,
                'col': col,
                'row': row,
                'cost': cost,
                'cost_percent': cost_percent,
            }
            stories_data.append(story_entry)
            gantt_data.append(story_entry)
        col += 1
    
    # Build dependencies list
    for story in stories_qs:
        for dep in story.dependencies.all():
            dependencies_data.append({
                'from_id': story.id,
                'to_id': dep.depends_on.id,
            })
    
    # All stories for the dropdown (unfiltered)
    all_stories = Story.objects.all().select_related('epic').order_by('epic__title', 'title')
    
    context = {
        'all_epics': all_epics,
        'epic_id': epic_id,
        'stories': stories_data,
        'dependencies': dependencies_data,
        'all_stories': all_stories,
        'gantt_data': gantt_data,
        'max_cost': max_cost,
        'stories_json': json.dumps(stories_data),
        'dependencies_json': json.dumps(dependencies_data),
    }
    return render(request, 'backlog/wbs.html', context)


@require_POST
def wbs_add_dependency(request):
    """Add a dependency via AJAX."""
    try:
        data = json.loads(request.body)
        story_id = data.get('story_id')
        depends_on_id = data.get('depends_on_id')
        
        if not story_id or not depends_on_id:
            return JsonResponse({'error': 'Missing story_id or depends_on_id'}, status=400)
        
        if str(story_id) == str(depends_on_id):
            return JsonResponse({'error': 'A story cannot depend on itself'}, status=400)
        
        story = get_object_or_404(Story, pk=story_id)
        depends_on = get_object_or_404(Story, pk=depends_on_id)
        
        # Check if dependency already exists
        if StoryDependency.objects.filter(story=story, depends_on=depends_on).exists():
            return JsonResponse({'error': 'Dependency already exists'}, status=400)
        
        StoryDependency.objects.create(story=story, depends_on=depends_on)
        return JsonResponse({'success': True, 'from_id': story.id, 'to_id': depends_on.id})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


@require_POST
def wbs_remove_dependency(request):
    """Remove a dependency via AJAX."""
    try:
        data = json.loads(request.body)
        story_id = data.get('story_id')
        depends_on_id = data.get('depends_on_id')
        
        if not story_id or not depends_on_id:
            return JsonResponse({'error': 'Missing story_id or depends_on_id'}, status=400)
        
        dep = StoryDependency.objects.filter(story_id=story_id, depends_on_id=depends_on_id).first()
        if dep:
            dep.delete()
            return JsonResponse({'success': True})
        return JsonResponse({'error': 'Dependency not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
