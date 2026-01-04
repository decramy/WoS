"""
Dashboard view for WoS backlog application.

Shows stories that need attention:
- Needs Scoring: Stories with missing value/cost factor scores
- Needs Refinement: Stories missing goal or workitems
- Rotting Stories: Stories stuck in started/planned for too long
- Review Required: Stories flagged for review
- Housekeeping: Data integrity issues (orphaned scores, etc.)
"""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from ..models import (
    CostFactor,
    Story,
    StoryCostFactorScore,
    StoryDependency,
    StoryHistory,
    StoryValueFactorScore,
    ValueFactor,
)


def dashboard(request):
    """Dashboard showing stories that need attention.
    
    Categories:
    - Needs Scoring: Stories with missing value/cost factor scores
    - Needs Refinement: Stories missing goal or workitems (status='idea')
    - Rotting Stories: Stories stuck in started/planned for too long
    - Review Required: Stories flagged for review
    - Housekeeping: Data integrity issues requiring cleanup
    """
    # Handle housekeeping cleanup actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cleanup_orphan_value_scores':
            # Delete value scores where the story doesn't exist
            deleted_count = StoryValueFactorScore.objects.exclude(
                story_id__in=Story.objects.values_list('id', flat=True)
            ).delete()[0]
            messages.success(request, f'🧹 Cleaned up {deleted_count} orphaned value factor scores.')
            return redirect('backlog:dashboard')
        
        if action == 'cleanup_orphan_cost_scores':
            # Delete cost scores where the story doesn't exist
            deleted_count = StoryCostFactorScore.objects.exclude(
                story_id__in=Story.objects.values_list('id', flat=True)
            ).delete()[0]
            messages.success(request, f'🧹 Cleaned up {deleted_count} orphaned cost factor scores.')
            return redirect('backlog:dashboard')
        
        if action == 'cleanup_orphan_dependencies':
            # Delete dependencies where story or depends_on doesn't exist
            valid_story_ids = set(Story.objects.values_list('id', flat=True))
            deleted_count = StoryDependency.objects.exclude(
                story_id__in=valid_story_ids
            ).delete()[0]
            deleted_count += StoryDependency.objects.exclude(
                depends_on_id__in=valid_story_ids
            ).delete()[0]
            messages.success(request, f'🧹 Cleaned up {deleted_count} orphaned dependencies.')
            return redirect('backlog:dashboard')
        
        if action == 'cleanup_orphan_history':
            # Delete history entries where the story doesn't exist
            deleted_count = StoryHistory.objects.exclude(
                story_id__in=Story.objects.values_list('id', flat=True)
            ).delete()[0]
            messages.success(request, f'🧹 Cleaned up {deleted_count} orphaned history entries.')
            return redirect('backlog:dashboard')
        
        if action == 'cleanup_stale_value_scores':
            # Delete value scores for factors that no longer exist
            valid_factor_ids = set(ValueFactor.objects.values_list('id', flat=True))
            deleted_count = StoryValueFactorScore.objects.exclude(
                valuefactor_id__in=valid_factor_ids
            ).delete()[0]
            messages.success(request, f'🧹 Cleaned up {deleted_count} scores for deleted value factors.')
            return redirect('backlog:dashboard')
        
        if action == 'cleanup_stale_cost_scores':
            # Delete cost scores for factors that no longer exist
            valid_factor_ids = set(CostFactor.objects.values_list('id', flat=True))
            deleted_count = StoryCostFactorScore.objects.exclude(
                costfactor_id__in=valid_factor_ids
            ).delete()[0]
            messages.success(request, f'🧹 Cleaned up {deleted_count} scores for deleted cost factors.')
            return redirect('backlog:dashboard')
    
    # Get all non-archived stories
    stories = Story.objects.filter(archived=False).prefetch_related(
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
    
    # ==========================================================================
    # Housekeeping: Detect data integrity issues
    # ==========================================================================
    housekeeping = {
        'issues': [],
        'total_issues': 0,
    }
    
    # Reuse all_value_factors and all_cost_factors loaded earlier for story scoring
    # Get all story IDs (including archived) for orphan detection
    all_story_ids = set(Story.objects.values_list('id', flat=True))
    
    # 1. Orphaned value factor scores (scores for deleted stories)
    orphan_value_scores = StoryValueFactorScore.objects.exclude(story_id__in=all_story_ids).count()
    if orphan_value_scores > 0:
        housekeeping['issues'].append({
            'type': 'orphan_value_scores',
            'icon': '🗑️',
            'title': 'Orphaned Value Scores',
            'description': 'Value scores for stories that no longer exist',
            'count': orphan_value_scores,
            'items': None,
            'action': 'cleanup_orphan_value_scores',
            'severity': 'info',
        })
    
    # 2. Orphaned cost factor scores (scores for deleted stories)
    orphan_cost_scores = StoryCostFactorScore.objects.exclude(story_id__in=all_story_ids).count()
    if orphan_cost_scores > 0:
        housekeeping['issues'].append({
            'type': 'orphan_cost_scores',
            'icon': '🗑️',
            'title': 'Orphaned Cost Scores',
            'description': 'Cost scores for stories that no longer exist',
            'count': orphan_cost_scores,
            'items': None,
            'action': 'cleanup_orphan_cost_scores',
            'severity': 'info',
        })
    
    # 3. Orphaned dependencies (dependencies referencing deleted stories)
    orphan_deps_from = StoryDependency.objects.exclude(story_id__in=all_story_ids).count()
    orphan_deps_to = StoryDependency.objects.exclude(depends_on_id__in=all_story_ids).count()
    orphan_deps_total = orphan_deps_from + orphan_deps_to
    if orphan_deps_total > 0:
        housekeeping['issues'].append({
            'type': 'orphan_dependencies',
            'icon': '🔗',
            'title': 'Orphaned Dependencies',
            'description': 'Dependencies referencing deleted stories',
            'count': orphan_deps_total,
            'items': None,
            'action': 'cleanup_orphan_dependencies',
            'severity': 'info',
        })
    
    # 5. Orphaned history entries (history for deleted stories)
    orphan_history = StoryHistory.objects.exclude(story_id__in=all_story_ids).count()
    if orphan_history > 0:
        housekeeping['issues'].append({
            'type': 'orphan_history',
            'icon': '📜',
            'title': 'Orphaned History',
            'description': 'History entries for stories that no longer exist',
            'count': orphan_history,
            'items': None,
            'action': 'cleanup_orphan_history',
            'severity': 'info',
        })
    
    # 6. Stale value scores (scores for deleted factors) - reuse all_value_factors
    stale_value_scores = StoryValueFactorScore.objects.exclude(valuefactor_id__in=all_value_factors).count()
    if stale_value_scores > 0:
        housekeeping['issues'].append({
            'type': 'stale_value_scores',
            'icon': '📊',
            'title': 'Stale Value Scores',
            'description': 'Scores for value factors that no longer exist',
            'count': stale_value_scores,
            'items': None,
            'action': 'cleanup_stale_value_scores',
            'severity': 'info',
        })
    
    # 7. Stale cost scores (scores for deleted factors) - reuse all_cost_factors
    stale_cost_scores = StoryCostFactorScore.objects.exclude(costfactor_id__in=all_cost_factors).count()
    if stale_cost_scores > 0:
        housekeeping['issues'].append({
            'type': 'stale_cost_scores',
            'icon': '📊',
            'title': 'Stale Cost Scores',
            'description': 'Scores for cost factors that no longer exist',
            'count': stale_cost_scores,
            'items': None,
            'action': 'cleanup_stale_cost_scores',
            'severity': 'info',
        })
    
    # 8. Duplicate dependencies (same dependency recorded multiple times)
    from django.db.models import Count as DjCount
    dup_deps = StoryDependency.objects.values('story', 'depends_on').annotate(
        cnt=DjCount('id')
    ).filter(cnt__gt=1)
    if dup_deps.exists():
        housekeeping['issues'].append({
            'type': 'duplicate_dependencies',
            'icon': '🔄',
            'title': 'Duplicate Dependencies',
            'description': 'Same dependency recorded multiple times',
            'count': sum(d['cnt'] - 1 for d in dup_deps),
            'items': None,
            'action': None,  # Would need special handling
            'severity': 'warning',
        })
    
    housekeeping['total_issues'] = sum(issue['count'] for issue in housekeeping['issues'])
    
    # ==========================================================================
    # Statistics: Informational metrics about the backlog
    # ==========================================================================
    
    # All stories (including archived)
    all_stories = Story.objects.all()
    
    # Story counts by status
    status_counts = {}
    for story in all_stories.filter(archived=False):
        status = story.computed_status
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Archived counts
    archived_stories = all_stories.filter(archived=True).count()
    
    # Recently completed stories (finished in last 30 days)
    recently_completed = all_stories.filter(
        archived=False,
        finished__isnull=False,
        finished__gte=now - timezone.timedelta(days=30)
    ).order_by('-finished')[:5]
    
    # Oldest open stories
    oldest_open = all_stories.filter(
        archived=False,
        finished__isnull=True
    ).order_by('created_at')[:5]
    
    # Stories with most dependencies
    stories_with_deps = []
    for story in stories:
        dep_count = story.dependencies.count()
        if dep_count > 0:
            stories_with_deps.append({'story': story, 'dependency_count': dep_count})
    stories_with_deps.sort(key=lambda x: x['dependency_count'], reverse=True)
    stories_with_deps = stories_with_deps[:5]
    
    # Stories blocking others (most dependents)
    blocking_stories = []
    for story in stories:
        dependent_count = story.dependents.count()
        if dependent_count > 0:
            blocking_stories.append({'story': story, 'dependent_count': dependent_count})
    blocking_stories.sort(key=lambda x: x['dependent_count'], reverse=True)
    blocking_stories = blocking_stories[:5]
    
    statistics = {
        'total_stories': all_stories.count(),
        'active_stories': all_stories.filter(archived=False).count(),
        'archived_stories': archived_stories,
        'status_counts': status_counts,
        'recently_completed': recently_completed,
        'oldest_open': oldest_open,
        'stories_with_deps': stories_with_deps,
        'blocking_stories': blocking_stories,
        'completion_rate_30d': recently_completed.count(),
    }
    
    # Summary counts
    summary = {
        'total_stories': stories.count(),
        'needs_scoring': len(needs_scoring),
        'needs_refinement': len(needs_refinement),
        'rotting': len(rotting_stories),
        'review_required': len(review_required),
        'housekeeping': housekeeping['total_issues'],
    }
    summary['healthy'] = summary['total_stories'] - len(set(
        [s['story'].id for s in needs_scoring] +
        [s['story'].id for s in needs_refinement] +
        [s['story'].id for s in rotting_stories] +
        [s['story'].id for s in review_required]
    ))
    
    context = {
        'review_required': review_required,  # First (most important)
        'needs_scoring': needs_scoring,
        'needs_refinement': needs_refinement,
        'rotting_stories': rotting_stories,
        'housekeeping': housekeeping,
        'statistics': statistics,
        'summary': summary,
        'thresholds': {
            'started_days': STARTED_ROTTING_DAYS,
            'planned_days': PLANNED_ROTTING_DAYS,
            'blocked_days': BLOCKED_ROTTING_DAYS,
        },
    }
    return render(request, 'backlog/dashboard.html', context)
