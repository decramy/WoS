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

from ..models import Story, StoryDependency
from .helpers import apply_label_filter, get_label_filter_context


def wbs_view(request):
    """Work Breakdown Structure showing stories with dependencies.
    
    Displays:
    - Stories in a grid layout
    - Dependency relationships between stories
    - Gantt-style bars showing relative cost/effort
    
    Supports AJAX dependency management.
    Supports filtering by labels (multi-select with OR logic).
    """
    # Get label filter context
    label_filter_ctx = get_label_filter_context(request)
    
    # Get stories (exclude archived)
    stories_qs = Story.objects.filter(archived=False).prefetch_related(
        'dependencies__depends_on', 'dependents__story', 'cost_scores__answer', 'labels__category'
    )
    
    # Apply label filter
    stories_qs = apply_label_filter(stories_qs, label_filter_ctx['selected_labels'])
    
    stories_qs = stories_qs.order_by('title')
    
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
    
    # Assign positions - simple row layout
    for row, story in enumerate(stories_qs):
        cost = story_costs.get(story.id, 0)
        cost_percent = (cost / max_cost * 100) if max_cost > 0 else 0
        
        story_entry = {
            'id': story.id,
            'title': story.title,
            'status': story.computed_status,
            'col': 0,
            'row': row,
            'cost': cost,
            'cost_percent': cost_percent,
        }
        stories_data.append(story_entry)
        gantt_data.append(story_entry)
    
    # Build dependencies list
    for story in stories_qs:
        for dep in story.dependencies.all():
            dependencies_data.append({
                'from_id': story.id,
                'to_id': dep.depends_on.id,
            })
    
    # All stories for the dropdown (unfiltered)
    all_stories = Story.objects.all().order_by('title')
    
    context = {
        'stories': stories_data,
        'dependencies': dependencies_data,
        'all_stories': all_stories,
        'gantt_data': gantt_data,
        'max_cost': max_cost,
        'stories_json': json.dumps(stories_data),
        'dependencies_json': json.dumps(dependencies_data),
        # Label filter context
        'label_categories': label_filter_ctx['label_categories'],
        'selected_labels': label_filter_ctx['selected_labels'],
        'selected_labels_objects': label_filter_ctx['selected_labels_objects'],
        'labels_param': label_filter_ctx['labels_param'],
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
