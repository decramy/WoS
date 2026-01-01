"""
Kanban board view for WoS backlog application.

Visual workflow board:
- kanban_view: Main kanban board with columns
- kanban_move: AJAX endpoint for drag-and-drop updates
"""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import Epic, Story
from .helpers import track_story_change
from .report import _calculate_story_score


def kanban_view(request):
    """Kanban board showing stories in workflow columns.
    
    Columns:
    - Backlog: Stories with 'ready' status
    - Planned: Stories with 'planned' status  
    - Doing: Stories with 'started' status
    - Blocked: Stories with 'blocked' status
    - Done: Stories with 'done' status
    
    Stories with 'idea' status are excluded from the board.
    
    Supports filtering by epic and sorting by result, status, or dates.
    """
    epic_id = request.GET.get('epic')
    sort_by = request.GET.get('sort', 'result')  # result, status, started, blocked, finished
    sort_order = request.GET.get('order', 'desc')
    all_epics = Epic.objects.filter(archived=False).order_by('title')

    qs = Story.objects.filter(archived=False).select_related('epic').prefetch_related('scores__answer', 'cost_scores__answer')
    if epic_id:
        qs = qs.filter(epic_id=epic_id)
    stories = list(qs)

    # Calculate scores for each story
    story_data = []
    for s in stories:
        score_info = _calculate_story_score(s)
        story_data.append({
            'story': s,
            'result': score_info['result'],
            'value': score_info['value'],
            'cost': score_info['cost'],
        })

    # Sort stories
    reverse = (sort_order == 'desc')
    if sort_by == 'result':
        story_data.sort(key=lambda x: x['result'], reverse=reverse)
    elif sort_by == 'started':
        story_data.sort(key=lambda x: (x['story'].started or timezone.datetime.min.replace(tzinfo=timezone.utc)), reverse=reverse)
    elif sort_by == 'finished':
        story_data.sort(key=lambda x: (x['story'].finished or timezone.datetime.min.replace(tzinfo=timezone.utc)), reverse=reverse)
    elif sort_by == 'blocked':
        story_data.sort(key=lambda x: x['story'].blocked or '', reverse=reverse)
    elif sort_by == 'status':
        status_order = {'idea': 0, 'ready': 1, 'planned': 2, 'started': 3, 'blocked': 4, 'done': 5}
        story_data.sort(key=lambda x: status_order.get(x['story'].computed_status, 0), reverse=reverse)

    columns = {
        'backlog': [],   # computed_status == 'ready'
        'planned': [],   # computed_status == 'planned'
        'doing': [],     # computed_status == 'started'
        'blocked': [],   # computed_status == 'blocked'
        'done': [],      # computed_status == 'done'
    }

    for item in story_data:
        s = item['story']
        st = s.computed_status
        card = {'story': s, 'result': item['result'], 'value': item['value'], 'cost': item['cost']}
        if st == 'ready':
            columns['backlog'].append(card)
        elif st == 'planned':
            columns['planned'].append(card)
        elif st == 'started':
            columns['doing'].append(card)
        elif st == 'blocked':
            columns['blocked'].append(card)
        elif st == 'done':
            columns['done'].append(card)
        # ignore 'idea' stories from the board

    context = {
        'columns': columns,
        'all_epics': all_epics,
        'epic_id': epic_id or '',
        'sort': sort_by,
        'order': sort_order,
    }
    return render(request, 'backlog/kanban.html', context)


@require_POST
def kanban_move(request):
    """Handle drag-and-drop move updates for stories.

    Expects JSON body: {story_id: int, target: 'backlog'|'planned'|'doing'|'blocked'|'done', blocked_reason?: str}
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        payload = request.POST

    story_id = payload.get('story_id')
    target = (payload.get('target') or '').strip()
    blocked_reason = (payload.get('blocked_reason') or '').strip()

    if not story_id or not target:
        return JsonResponse({'ok': False, 'error': 'Missing story_id or target'}, status=400)

    story = get_object_or_404(Story, pk=story_id)
    
    # Store old values for history tracking
    old_status = story.computed_status
    old_planned = story.planned
    old_started = story.started
    old_finished = story.finished
    old_blocked = story.blocked

    # Apply changes based on target column
    if target == 'backlog':
        story.planned = None
        story.started = None
        story.finished = None
        story.blocked = ''
    elif target == 'planned':
        story.planned = timezone.now()
        # do not clear started/finished explicitly; planned status takes effect if others unset
        story.blocked = ''
    elif target == 'doing':
        story.started = timezone.now()
        story.blocked = ''
    elif target == 'blocked':
        story.blocked = blocked_reason or 'Blocked'
    elif target == 'done':
        story.finished = timezone.now()
        story.blocked = ''
    else:
        return JsonResponse({'ok': False, 'error': 'Invalid target'}, status=400)

    story.save()
    
    # Track history changes
    new_status = story.computed_status
    if old_status != new_status:
        track_story_change(story, 'Status (Kanban)', old_status.upper(), new_status.upper())
    
    # Track date changes
    if old_planned != story.planned:
        old_val = old_planned.strftime('%Y-%m-%d %H:%M') if old_planned else None
        new_val = story.planned.strftime('%Y-%m-%d %H:%M') if story.planned else None
        track_story_change(story, 'Planned', old_val, new_val)
    
    if old_started != story.started:
        old_val = old_started.strftime('%Y-%m-%d %H:%M') if old_started else None
        new_val = story.started.strftime('%Y-%m-%d %H:%M') if story.started else None
        track_story_change(story, 'Started', old_val, new_val)
    
    if old_finished != story.finished:
        old_val = old_finished.strftime('%Y-%m-%d %H:%M') if old_finished else None
        new_val = story.finished.strftime('%Y-%m-%d %H:%M') if story.finished else None
        track_story_change(story, 'Finished', old_val, new_val)
    
    if old_blocked != story.blocked:
        track_story_change(story, 'Blocked', old_blocked if old_blocked else None, story.blocked if story.blocked else None)
    
    return JsonResponse({
        'ok': True,
        'story': {
            'id': story.id,
            'status': story.computed_status,
            'planned': story.planned.isoformat() if story.planned else None,
            'started': story.started.isoformat() if story.started else None,
            'finished': story.finished.isoformat() if story.finished else None,
            'blocked': story.blocked,
        }
    })
