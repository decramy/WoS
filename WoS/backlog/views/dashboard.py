"""
Dashboard view for WoS backlog application.

Shows stories that need attention:
- Needs Scoring: Stories with missing value/cost factor scores
- Needs Refinement: Stories missing goal or workitems
- Rotting Stories: Stories stuck in started/planned for too long
- Review Required: Stories flagged for review
"""
from django.shortcuts import render
from django.utils import timezone

from ..models import (
    CostFactor,
    Story,
    ValueFactor,
)


def dashboard(request):
    """Dashboard showing stories that need attention.
    
    Categories:
    - Needs Scoring: Stories with missing value/cost factor scores
    - Needs Refinement: Stories missing goal or workitems (status='idea')
    - Rotting Stories: Stories stuck in started/planned for too long
    - Review Required: Stories flagged for review
    """
    # Get all non-archived stories
    stories = Story.objects.filter(archived=False).select_related('epic').prefetch_related(
        'scores', 'cost_scores'
    )
    
    # Get all factors to check completeness
    all_value_factors = set(ValueFactor.objects.values_list('id', flat=True))
    all_cost_factors = set(CostFactor.objects.values_list('id', flat=True))
    
    # Rotting thresholds (configurable)
    STARTED_ROTTING_DAYS = 14  # Started but not done for 14+ days
    PLANNED_ROTTING_DAYS = 30  # Planned but not started for 30+ days
    BLOCKED_ROTTING_DAYS = 7   # Blocked for 7+ days
    
    now = timezone.now()
    
    needs_scoring = []
    needs_refinement = []
    rotting_stories = []
    review_required = []
    
    for story in stories:
        # Check if needs scoring - either missing factor records OR answer=None (undefined)
        story_vf_ids = set(
            score.valuefactor_id for score in story.scores.all() 
            if score.answer is not None
        )
        story_cf_ids = set(
            score.costfactor_id for score in story.cost_scores.all()
            if score.answer is not None
        )
        
        missing_value = all_value_factors - story_vf_ids
        missing_cost = all_cost_factors - story_cf_ids
        
        if missing_value or missing_cost:
            needs_scoring.append({
                'story': story,
                'missing_value_count': len(missing_value),
                'missing_cost_count': len(missing_cost),
            })
        
        # Check if needs refinement (idea status = missing goal/workitems)
        computed = story.computed_status
        if computed == 'idea':
            missing = []
            if not story.goal or not story.goal.strip():
                missing.append('goal')
            if not story.workitems or not story.workitems.strip():
                missing.append('workitems')
            needs_refinement.append({
                'story': story,
                'missing': missing,
            })
        
        # Check for rotting stories
        if computed == 'started' and story.started:
            days_since_started = (now - story.started).days
            if days_since_started >= STARTED_ROTTING_DAYS:
                rotting_stories.append({
                    'story': story,
                    'reason': 'started',
                    'days': days_since_started,
                })
        elif computed == 'planned' and story.planned:
            days_since_planned = (now - story.planned).days
            if days_since_planned >= PLANNED_ROTTING_DAYS:
                rotting_stories.append({
                    'story': story,
                    'reason': 'planned',
                    'days': days_since_planned,
                })
        elif computed == 'blocked' and story.updated_at:
            days_blocked = (now - story.updated_at).days
            if days_blocked >= BLOCKED_ROTTING_DAYS:
                rotting_stories.append({
                    'story': story,
                    'reason': 'blocked',
                    'days': days_blocked,
                    'blocked_reason': story.blocked,
                })
        
        # Check if review required
        if story.review_required:
            review_required.append({'story': story})
    
    # Sort rotting stories by days (most stale first)
    rotting_stories.sort(key=lambda x: x['days'], reverse=True)
    
    # Summary counts
    summary = {
        'total_stories': stories.count(),
        'needs_scoring': len(needs_scoring),
        'needs_refinement': len(needs_refinement),
        'rotting': len(rotting_stories),
        'review_required': len(review_required),
    }
    summary['healthy'] = summary['total_stories'] - len(set(
        [s['story'].id for s in needs_scoring] +
        [s['story'].id for s in needs_refinement] +
        [s['story'].id for s in rotting_stories] +
        [s['story'].id for s in review_required]
    ))
    
    context = {
        'needs_scoring': needs_scoring,
        'needs_refinement': needs_refinement,
        'rotting_stories': rotting_stories,
        'review_required': review_required,
        'summary': summary,
        'thresholds': {
            'started_days': STARTED_ROTTING_DAYS,
            'planned_days': PLANNED_ROTTING_DAYS,
            'blocked_days': BLOCKED_ROTTING_DAYS,
        },
    }
    return render(request, 'backlog/dashboard.html', context)
