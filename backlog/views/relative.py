"""
Relative ranking view for WoS backlog application.

Provides a UI to rank stories relative to each other for a specific factor:
- relative_ranking: Main page to select factor and rank stories
- relative_ranking_save: AJAX endpoint to save rankings
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import (
    CostFactor,
    Story,
    StoryCostFactorScore,
    StoryValueFactorScore,
    ValueFactor,
)


def relative_ranking(request):
    """Relative ranking page for scoring stories against each other.
    
    Allows selecting a value or cost factor, then dragging stories
    to rank them relative to each other within that factor.
    Only shows factors with scoring_mode='relative'.
    """
    # Get only factors with scoring_mode='relative' for the dropdown
    value_factors = ValueFactor.objects.filter(
        scoring_mode=ValueFactor.SCORING_RELATIVE
    ).select_related('section').order_by('section__name', 'name')
    cost_factors = CostFactor.objects.filter(
        scoring_mode=CostFactor.SCORING_RELATIVE
    ).select_related('section').order_by('section__name', 'name')
    
    # Get selected factor from query params
    factor_type = request.GET.get('type', 'value')  # 'value' or 'cost'
    factor_id = request.GET.get('factor', '')
    
    selected_factor = None
    stories_data = []
    answer_boundaries = []
    
    if factor_id:
        try:
            factor_id = int(factor_id)
            if factor_type == 'value':
                selected_factor = ValueFactor.objects.select_related('section').prefetch_related('answers').get(pk=factor_id)
                # Get all non-archived stories with their scores for this factor
                scores = StoryValueFactorScore.objects.filter(
                    valuefactor=selected_factor,
                    story__archived=False
                ).select_related('story', 'answer').order_by('relative_rank')
                
                # Build answer boundaries (score levels)
                answers = list(selected_factor.answers.order_by('-score'))  # Highest score first
                answer_boundaries = [{'id': a.id, 'score': a.score, 'description': a.description} for a in answers]
                
            else:
                selected_factor = CostFactor.objects.select_related('section').prefetch_related('answers').get(pk=factor_id)
                scores = StoryCostFactorScore.objects.filter(
                    costfactor=selected_factor,
                    story__archived=False
                ).select_related('story', 'answer').order_by('relative_rank')
                
                # Build answer boundaries (score levels) - for cost, lower is better
                answers = list(selected_factor.answers.order_by('score'))  # Lowest score first (best)
                answer_boundaries = [{'id': a.id, 'score': a.score, 'description': a.description} for a in answers]
            
            # Get all stories that have a score record for this factor
            stories_with_scores = {score.story_id for score in scores}
            
            # Get all non-archived stories that DON'T have a score record yet
            # These need to have score records created
            all_stories = Story.objects.filter(archived=False).exclude(id__in=stories_with_scores)
            
            # Create score records for stories that don't have them
            if factor_type == 'value':
                for story in all_stories:
                    StoryValueFactorScore.objects.get_or_create(
                        story=story,
                        valuefactor=selected_factor,
                        defaults={'answer': None, 'relative_rank': None}
                    )
                # Re-fetch scores after creating missing ones
                scores = StoryValueFactorScore.objects.filter(
                    valuefactor=selected_factor,
                    story__archived=False
                ).select_related('story', 'answer').order_by('relative_rank')
            else:
                for story in all_stories:
                    StoryCostFactorScore.objects.get_or_create(
                        story=story,
                        costfactor=selected_factor,
                        defaults={'answer': None, 'relative_rank': None}
                    )
                # Re-fetch scores after creating missing ones
                scores = StoryCostFactorScore.objects.filter(
                    costfactor=selected_factor,
                    story__archived=False
                ).select_related('story', 'answer').order_by('relative_rank')
            
            # Separate into three categories:
            # 1. ranked: has a relative_rank (positive integer)
            # 2. undefined: relative_rank is None (not yet ranked - needs attention)
            # 3. no_score: relative_rank is 0 (explicitly marked as "doesn't apply")
            ranked_stories = []
            undefined_stories = []
            no_score_stories = []
            
            for score in scores:
                story_info = {
                    'id': score.story.id,
                    'title': score.story.title,
                    'answer_id': score.answer_id,
                    'answer_score': score.answer.score if score.answer else None,
                    'answer_desc': score.answer.description if score.answer else 'Undefined',
                    'relative_rank': score.relative_rank,
                }
                if score.relative_rank is not None and score.relative_rank > 0:
                    ranked_stories.append(story_info)
                elif score.relative_rank == 0:
                    # Explicit "no score" marker
                    no_score_stories.append(story_info)
                else:
                    # None = undefined, needs ranking
                    undefined_stories.append(story_info)
            
            # Sort ranked by rank
            ranked_stories.sort(key=lambda x: x['relative_rank'])
            
            # Sort undefined by answer score (descending for value, ascending for cost)
            if factor_type == 'value':
                # Higher answer score = better = should be at top
                undefined_stories.sort(key=lambda x: (x['answer_score'] is None, -(x['answer_score'] or 0)))
                no_score_stories.sort(key=lambda x: (x['answer_score'] is None, -(x['answer_score'] or 0)))
            else:
                # Lower answer score = better = should be at top
                undefined_stories.sort(key=lambda x: (x['answer_score'] is None, x['answer_score'] or 999))
                no_score_stories.sort(key=lambda x: (x['answer_score'] is None, x['answer_score'] or 999))
            
            stories_data = {
                'ranked': ranked_stories,
                'undefined': undefined_stories,
                'no_score': no_score_stories,
            }
            
        except (ValueError, ValueFactor.DoesNotExist, CostFactor.DoesNotExist):
            pass
    
    context = {
        'value_factors': value_factors,
        'cost_factors': cost_factors,
        'factor_type': factor_type,
        'factor_id': factor_id,
        'selected_factor': selected_factor,
        'stories_data': json.dumps(stories_data) if stories_data else '{}',
        'answer_boundaries': json.dumps(answer_boundaries),
    }
    return render(request, 'backlog/relative.html', context)


@require_POST
def relative_ranking_save(request):
    """AJAX endpoint to save relative rankings for a factor.
    
    Expects JSON body:
    {
        "factor_type": "value" | "cost",
        "factor_id": int,
        "rankings": [
            {"story_id": int, "rank": int},
            ...
        ]
    }
    """
    try:
        data = json.loads(request.body)
        factor_type = data.get('factor_type')
        factor_id = data.get('factor_id')
        rankings = data.get('rankings', [])
        
        if factor_type == 'value':
            factor = ValueFactor.objects.get(pk=factor_id)
            for item in rankings:
                StoryValueFactorScore.objects.filter(
                    story_id=item['story_id'],
                    valuefactor=factor
                ).update(relative_rank=item['rank'])
        else:
            factor = CostFactor.objects.get(pk=factor_id)
            for item in rankings:
                StoryCostFactorScore.objects.filter(
                    story_id=item['story_id'],
                    costfactor=factor
                ).update(relative_rank=item['rank'])
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
