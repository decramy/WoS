"""
Hybrid Report view for WoS backlog application.

WSJF scoring report combining absolute and relative scoring:
- Factors with scoring_mode='absolute' use their answer.score
- Factors with scoring_mode='relative' use their relative_rank, normalized to answer scale

The formula remains the same:
  Result = sum(value_section_averages) / sum(cost_section_averages)
  
Normalization for relative ranks:
  - Gets min/max scores from factor's answer options
  - Maps rank 1 → max_score, rank N → min_score (linear interpolation)
  - For value: rank 1 = best = highest score
  - For cost: rank 1 = best = lowest score (inverted)
"""
from django.db.models import Max, Min, Count, Q
from django.shortcuts import render

from ..models import (
    CostFactor,
    CostFactorSection,
    Story,
    StoryCostFactorScore,
    StoryValueFactorScore,
    ValueFactor,
    ValueFactorSection,
)
from .helpers import apply_label_filter, get_label_filter_context


def _get_factor_score_ranges():
    """Get min/max answer scores for each factor.
    
    Returns:
        value_ranges: dict of {factor_id: {'min': int, 'max': int}}
        cost_ranges: dict of {factor_id: {'min': int, 'max': int}}
    """
    value_ranges = {}
    for vf in ValueFactor.objects.prefetch_related('answers').all():
        scores = [a.score for a in vf.answers.all()]
        if scores:
            value_ranges[vf.id] = {'min': min(scores), 'max': max(scores)}
        else:
            value_ranges[vf.id] = {'min': 1, 'max': 5}  # default
    
    cost_ranges = {}
    for cf in CostFactor.objects.prefetch_related('answers').all():
        scores = [a.score for a in cf.answers.all()]
        if scores:
            cost_ranges[cf.id] = {'min': min(scores), 'max': max(scores)}
        else:
            cost_ranges[cf.id] = {'min': 1, 'max': 5}  # default
    
    return value_ranges, cost_ranges


def _get_ranked_counts(story_ids):
    """Get count of ranked stories (relative_rank > 0) per factor.
    
    Args:
        story_ids: List of story IDs to consider (filtered stories)
    
    Returns:
        value_counts: dict of {factor_id: count}
        cost_counts: dict of {factor_id: count}
    """
    # Count ranked stories per value factor
    value_counts = {}
    value_stats = StoryValueFactorScore.objects.filter(
        story_id__in=story_ids,
        relative_rank__gt=0
    ).values('valuefactor_id').annotate(count=Count('id'))
    for stat in value_stats:
        value_counts[stat['valuefactor_id']] = stat['count']
    
    # Count ranked stories per cost factor
    cost_counts = {}
    cost_stats = StoryCostFactorScore.objects.filter(
        story_id__in=story_ids,
        relative_rank__gt=0
    ).values('costfactor_id').annotate(count=Count('id'))
    for stat in cost_stats:
        cost_counts[stat['costfactor_id']] = stat['count']
    
    return value_counts, cost_counts


def _normalize_rank(rank, ranked_count, min_score, max_score, invert=False):
    """Normalize a rank to a score within the answer scale.
    
    Args:
        rank: The relative rank (1 = best)
        ranked_count: Total number of ranked stories for this factor
        min_score: Minimum answer score for this factor
        max_score: Maximum answer score for this factor
        invert: If True, rank 1 → min_score (for cost factors)
                If False, rank 1 → max_score (for value factors)
    
    Returns:
        Normalized score (float)
    """
    if ranked_count <= 1:
        # Only one story ranked, give it the best score
        return min_score if invert else max_score
    
    # Linear interpolation: rank 1 → best, rank N → worst
    # For value: best = max_score, worst = min_score
    # For cost: best = min_score, worst = max_score
    t = (rank - 1) / (ranked_count - 1)  # 0 for rank 1, 1 for rank N
    
    if invert:
        # Cost: rank 1 → min_score, rank N → max_score
        return min_score + t * (max_score - min_score)
    else:
        # Value: rank 1 → max_score, rank N → min_score
        return max_score - t * (max_score - min_score)


def relative_report_view(request):
    """Hybrid WSJF scoring report combining absolute and relative scoring.
    
    Each factor can be set to 'absolute' or 'relative' scoring mode:
    - absolute: uses answer.score directly
    - relative: uses relative_rank, normalized to the factor's answer scale
    
    Formula:
    - Per-section average = avg of all factor scores in that section
    - Total value = sum of value section averages
    - Total cost = sum of cost section averages  
    - Result = total value / total cost
    
    For relative factors (normalized):
    - Value: rank 1 → max_score, rank N → min_score (higher = better)
    - Cost: rank 1 → min_score, rank N → max_score (lower = better)
    """
    # Get label filter context
    label_filter_ctx = get_label_filter_context(request)
    status_filter = request.GET.get('status', '')
    
    value_sections = list(
        ValueFactorSection.objects.prefetch_related("valuefactors").order_by("name")
    )
    cost_sections = list(
        CostFactorSection.objects.prefetch_related("costfactors").order_by("name")
    )

    stories_qs = (
        Story.objects.filter(archived=False)
        .prefetch_related(
            "scores__valuefactor",
            "scores__answer",
            "cost_scores__costfactor", 
            "cost_scores__answer",
            "labels__category"
        )
        .order_by("title")
    )
    
    # Apply label filter
    stories_qs = apply_label_filter(stories_qs, label_filter_ctx['selected_labels'])
    
    # Status filtering requires post-processing since computed_status is a property
    if status_filter:
        stories_qs = [s for s in stories_qs if s.computed_status == status_filter]
    else:
        stories_qs = list(stories_qs)

    # Get IDs of filtered stories for rank counting
    story_ids = [s.id for s in stories_qs]
    total_story_count = len(stories_qs)
    
    # Get score ranges and ranked counts for normalization
    value_ranges, cost_ranges = _get_factor_score_ranges()
    value_ranked_counts, cost_ranked_counts = _get_ranked_counts(story_ids)
    
    # Check if we have any relative factors
    has_relative_value_factors = ValueFactor.objects.filter(scoring_mode=ValueFactor.SCORING_RELATIVE).exists()
    has_relative_cost_factors = CostFactor.objects.filter(scoring_mode=CostFactor.SCORING_RELATIVE).exists()
    has_any_relative = has_relative_value_factors or has_relative_cost_factors
    
    rows = []
    for s in stories_qs:
        # Build maps for both absolute and relative scoring
        # vf_map: factor_id -> {score, relative_rank, answer_desc, scoring_mode}
        vf_map = {}
        for sv in s.scores.all():
            vf_map[sv.valuefactor_id] = {
                'score': sv.answer.score if sv.answer else None,
                'relative_rank': sv.relative_rank,
                'answer_desc': sv.answer.description if sv.answer else 'Undefined',
                'scoring_mode': sv.valuefactor.scoring_mode,
            }
        
        cf_map = {}
        for sv in s.cost_scores.all():
            cf_map[sv.costfactor_id] = {
                'score': sv.answer.score if sv.answer else None,
                'relative_rank': sv.relative_rank,
                'answer_desc': sv.answer.description if sv.answer else 'Undefined',
                'scoring_mode': sv.costfactor.scoring_mode,
            }

        # per-value-section averages with breakdown details for tooltips
        value_section_data = []
        for vs in value_sections:
            factors_detail = []
            scores = []
            for vf in vs.valuefactors.all():
                factor_info = vf_map.get(vf.id)
                if factor_info:
                    scoring_mode = factor_info['scoring_mode']
                    
                    if scoring_mode == ValueFactor.SCORING_ABSOLUTE:
                        # Use absolute score
                        if factor_info['score'] is not None:
                            scores.append(factor_info['score'])
                            factors_detail.append({
                                'name': vf.name,
                                'description': vf.description,
                                'score': factor_info['score'],
                                'mode': 'absolute',
                                'answer_description': factor_info['answer_desc']
                            })
                        else:
                            factors_detail.append({
                                'name': vf.name,
                                'description': vf.description,
                                'score': None,
                                'mode': 'absolute',
                                'answer_description': factor_info['answer_desc']
                            })
                    else:
                        # Use relative rank, normalized to answer scale
                        rank = factor_info['relative_rank']
                        if rank is not None and rank > 0:
                            # Get normalization params
                            score_range = value_ranges.get(vf.id, {'min': 1, 'max': 5})
                            ranked_count = value_ranked_counts.get(vf.id, 1)
                            
                            # Normalize: rank 1 → max_score, rank N → min_score
                            normalized = _normalize_rank(
                                rank, ranked_count,
                                score_range['min'], score_range['max'],
                                invert=False  # Value: higher = better
                            )
                            scores.append(normalized)
                            factors_detail.append({
                                'name': vf.name,
                                'description': vf.description,
                                'score': normalized,
                                'rank': rank,
                                'ranked_count': ranked_count,
                                'mode': 'relative',
                                'answer_description': factor_info['answer_desc']
                            })
                        else:
                            factors_detail.append({
                                'name': vf.name,
                                'description': vf.description,
                                'score': None,
                                'rank': rank,
                                'mode': 'relative',
                                'answer_description': factor_info['answer_desc']
                            })
                else:
                    factors_detail.append({
                        'name': vf.name,
                        'description': vf.description,
                        'score': None,
                        'mode': vf.scoring_mode,
                        'answer_description': 'Undefined'
                    })
            
            if scores:
                avg = sum(scores) / len(scores)
                # Build tooltip
                tooltip_lines = []
                for f in factors_detail:
                    if f['score'] is not None:
                        if f['mode'] == 'absolute':
                            line = f"• {f['name']}: {f['score']} ({f['answer_description']})"
                        else:
                            ranked_count = f.get('ranked_count', '?')
                            line = f"• {f['name']}: #{f.get('rank', '?')}/{ranked_count} → {f['score']:.1f} [relative]"
                        tooltip_lines.append(line)
                    else:
                        mode_hint = "[relative]" if f['mode'] == 'relative' else ""
                        tooltip_lines.append(f"• {f['name']}: — {mode_hint}")
                tooltip_lines.append(f"\nAverage: {sum(scores):.1f} ÷ {len(scores)} = {avg:.1f}")
                value_section_data.append({
                    'avg': avg,
                    'factors': factors_detail,
                    'tooltip': '\n'.join(tooltip_lines)
                })
            else:
                tooltip_lines = []
                for f in factors_detail:
                    mode_hint = "[relative]" if f['mode'] == 'relative' else ""
                    tooltip_lines.append(f"• {f['name']}: — {mode_hint}")
                tooltip_lines.append('\nNo scores set')
                value_section_data.append({'avg': None, 'factors': factors_detail, 'tooltip': '\n'.join(tooltip_lines)})

        # per-cost-section averages with breakdown details for tooltips
        cost_section_data = []
        for cs in cost_sections:
            factors_detail = []
            scores = []
            for cf in cs.costfactors.all():
                factor_info = cf_map.get(cf.id)
                if factor_info:
                    scoring_mode = factor_info['scoring_mode']
                    
                    if scoring_mode == CostFactor.SCORING_ABSOLUTE:
                        # Use absolute score
                        if factor_info['score'] is not None:
                            scores.append(factor_info['score'])
                            factors_detail.append({
                                'name': cf.name,
                                'description': cf.description,
                                'score': factor_info['score'],
                                'mode': 'absolute',
                                'answer_description': factor_info['answer_desc']
                            })
                        else:
                            factors_detail.append({
                                'name': cf.name,
                                'description': cf.description,
                                'score': None,
                                'mode': 'absolute',
                                'answer_description': factor_info['answer_desc']
                            })
                    else:
                        # Use relative rank, normalized to answer scale
                        rank = factor_info['relative_rank']
                        if rank is not None and rank > 0:
                            # Get normalization params
                            score_range = cost_ranges.get(cf.id, {'min': 1, 'max': 5})
                            ranked_count = cost_ranked_counts.get(cf.id, 1)
                            
                            # Normalize: rank 1 → min_score, rank N → max_score
                            # (for cost, lower is better, so rank 1 = best = low score)
                            normalized = _normalize_rank(
                                rank, ranked_count,
                                score_range['min'], score_range['max'],
                                invert=True  # Cost: lower = better
                            )
                            scores.append(normalized)
                            factors_detail.append({
                                'name': cf.name,
                                'description': cf.description,
                                'score': normalized,
                                'rank': rank,
                                'ranked_count': ranked_count,
                                'mode': 'relative',
                                'answer_description': factor_info['answer_desc']
                            })
                        else:
                            factors_detail.append({
                                'name': cf.name,
                                'description': cf.description,
                                'score': None,
                                'rank': rank,
                                'mode': 'relative',
                                'answer_description': factor_info['answer_desc']
                            })
                else:
                    factors_detail.append({
                        'name': cf.name,
                        'description': cf.description,
                        'score': None,
                        'mode': cf.scoring_mode,
                        'answer_description': 'Undefined'
                    })
            
            if scores:
                avg = sum(scores) / len(scores)
                # Build tooltip
                tooltip_lines = []
                for f in factors_detail:
                    if f['score'] is not None:
                        if f['mode'] == 'absolute':
                            line = f"• {f['name']}: {f['score']} ({f['answer_description']})"
                        else:
                            ranked_count = f.get('ranked_count', '?')
                            line = f"• {f['name']}: #{f.get('rank', '?')}/{ranked_count} → {f['score']:.1f} [relative]"
                        tooltip_lines.append(line)
                    else:
                        mode_hint = "[relative]" if f['mode'] == 'relative' else ""
                        tooltip_lines.append(f"• {f['name']}: — {mode_hint}")
                tooltip_lines.append(f"\nAverage: {sum(scores):.1f} ÷ {len(scores)} = {avg:.1f}")
                cost_section_data.append({
                    'avg': avg,
                    'factors': factors_detail,
                    'tooltip': '\n'.join(tooltip_lines)
                })
            else:
                tooltip_lines = []
                for f in factors_detail:
                    mode_hint = "[relative]" if f['mode'] == 'relative' else ""
                    tooltip_lines.append(f"• {f['name']}: — {mode_hint}")
                tooltip_lines.append('\nNo scores set')
                cost_section_data.append({'avg': None, 'factors': factors_detail, 'tooltip': '\n'.join(tooltip_lines)})

        # Extract just the averages
        value_section_avgs = [d['avg'] for d in value_section_data]
        cost_section_avgs = [d['avg'] for d in cost_section_data]

        # Total Value = sum of section averages
        value_sum = sum(avg for avg in value_section_avgs if avg is not None)
        # Total Cost = sum of section averages
        cost_sum = sum(avg for avg in cost_section_avgs if avg is not None)
        
        # Build tooltip for totals
        value_total_tooltip = ' + '.join(f"{value_sections[i].name}: {d['avg']:.1f}" for i, d in enumerate(value_section_data) if d['avg'] is not None)
        if value_total_tooltip:
            value_total_tooltip += f" = {value_sum:.1f}"
        else:
            value_total_tooltip = "No section scores"
            
        cost_total_tooltip = ' + '.join(f"{cost_sections[i].name}: {d['avg']:.1f}" for i, d in enumerate(cost_section_data) if d['avg'] is not None)
        if cost_total_tooltip:
            cost_total_tooltip += f" = {cost_sum:.1f}"
        else:
            cost_total_tooltip = "No section scores"
        
        result = None
        if cost_sum:
            try:
                result = value_sum / cost_sum
            except Exception:
                result = None

        # Result class for coloring
        if result is None:
            result_class = "neutral"
        else:
            result_class = "good" if result >= 1 else "bad"
            
        # Build result tooltip
        if result is not None:
            result_tooltip = f"Value ({value_sum:.1f}) ÷ Cost ({cost_sum:.1f}) = {result:.2f}"
        else:
            result_tooltip = "Cannot calculate (no cost scores)"
        
        # Check if story has scores
        has_scores = any(d['avg'] is not None for d in value_section_data) or any(d['avg'] is not None for d in cost_section_data)

        rows.append(
            {
                "story": s,
                "value_section_data": value_section_data,
                "cost_section_data": cost_section_data,
                "value_section_avgs": value_section_avgs,
                "cost_section_avgs": cost_section_avgs,
                "value_sum": value_sum,
                "cost_sum": cost_sum,
                "value_total_tooltip": value_total_tooltip,
                "cost_total_tooltip": cost_total_tooltip,
                "result": result,
                "result_tooltip": result_tooltip,
                "result_class": result_class,
                "has_scores": has_scores,
            }
        )

    context = {
        "value_sections": value_sections,
        "cost_sections": cost_sections,
        "rows": rows,
        "total_cols": 5 + len(value_sections) + len(cost_sections),
        "status_filter": status_filter,
        "total_story_count": total_story_count,
        "has_any_relative": has_any_relative,
        # Label filter context
        "label_categories": label_filter_ctx['label_categories'],
        "selected_labels": label_filter_ctx['selected_labels'],
        "selected_labels_objects": label_filter_ctx['selected_labels_objects'],
        "labels_param": label_filter_ctx['labels_param'],
    }
    return render(request, "backlog/relative_report.html", context)
