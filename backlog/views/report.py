"""
Report view for WoS backlog application.

WSJF scoring report showing value/cost breakdown and prioritization:
- report_view: Main report with section averages and tooltips
- _calculate_story_score: Helper to calculate value/cost score
"""
from django.shortcuts import render

from ..models import (
    CostFactorSection,
    Story,
    ValueFactorSection,
)
from .helpers import apply_label_filter, get_label_filter_context


def report_view(request):
    """WSJF scoring report showing value/cost breakdown and prioritization.
    
    Calculates for each story:
    - Per-section average scores for value and cost factors
    - Total value = sum of value section averages
    - Total cost = sum of cost section averages  
    - Result = total value / total cost (WSJF score)
    
    Features:
    - Filter by computed status
    - Filter by labels (multi-select with OR logic)
    - Tooltips showing factor breakdown for each section
    - Tweak mode for temporary score adjustments
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
        Story.objects.filter(archived=False).prefetch_related("scores__answer", "cost_scores__answer", "labels__category").order_by(
            "title",
        )
    )
    
    # Apply label filter
    stories_qs = apply_label_filter(stories_qs, label_filter_ctx['selected_labels'])
    
    # Status filtering requires post-processing since computed_status is a property
    if status_filter:
        stories_qs = [s for s in stories_qs if s.computed_status == status_filter]
    else:
        stories_qs = list(stories_qs)

    rows = []
    for s in stories_qs:
        # maps of factor id -> (score, answer_description), only for defined scores
        vf_map = {
            sv.valuefactor_id: (sv.answer.score, sv.answer.description)
            for sv in s.scores.all() if sv.answer
        }
        cf_map = {
            sv.costfactor_id: (sv.answer.score, sv.answer.description)
            for sv in s.cost_scores.all() if sv.answer
        }

        # per-value-section averages with breakdown details for tooltips
        value_section_data = []
        for vs in value_sections:
            factors_detail = []
            vals = []
            for vf in vs.valuefactors.all():
                score_info = vf_map.get(vf.id)
                if score_info is not None:
                    sc, answer_desc = score_info
                    vals.append(sc)
                    factors_detail.append({
                        'name': vf.name,
                        'description': vf.description,
                        'score': sc,
                        'answer_description': answer_desc
                    })
                else:
                    factors_detail.append({
                        'name': vf.name,
                        'description': vf.description,
                        'score': None,
                        'answer_description': None
                    })
            if vals:
                avg = sum(vals) / len(vals)
                # Build multi-line tooltip with factor details
                tooltip_lines = []
                for f in factors_detail:
                    if f['score'] is not None:
                        line = f"• {f['name']}: {f['score']}"
                        if f['answer_description']:
                            line += f" ({f['answer_description']})"
                        if f['description']:
                            line += f"\n  {f['description']}"
                        tooltip_lines.append(line)
                    else:
                        tooltip_lines.append(f"• {f['name']}: —")
                tooltip_lines.append(f"\nAverage: {sum(vals)} ÷ {len(vals)} = {avg:.1f}")
                value_section_data.append({
                    'avg': avg,
                    'factors': factors_detail,
                    'tooltip': '\n'.join(tooltip_lines)
                })
            else:
                tooltip_lines = [f"• {f['name']}: —" for f in factors_detail]
                tooltip_lines.append('\nNo scores set')
                value_section_data.append({'avg': None, 'factors': factors_detail, 'tooltip': '\n'.join(tooltip_lines)})

        # per-cost-section averages with breakdown details for tooltips
        cost_section_data = []
        for cs in cost_sections:
            factors_detail = []
            vals = []
            for cf in cs.costfactors.all():
                score_info = cf_map.get(cf.id)
                if score_info is not None:
                    sc, answer_desc = score_info
                    vals.append(sc)
                    factors_detail.append({
                        'name': cf.name,
                        'description': cf.description,
                        'score': sc,
                        'answer_description': answer_desc
                    })
                else:
                    factors_detail.append({
                        'name': cf.name,
                        'description': cf.description,
                        'score': None,
                        'answer_description': None
                    })
            if vals:
                avg = sum(vals) / len(vals)
                # Build multi-line tooltip with factor details
                tooltip_lines = []
                for f in factors_detail:
                    if f['score'] is not None:
                        line = f"• {f['name']}: {f['score']}"
                        if f['answer_description']:
                            line += f" ({f['answer_description']})"
                        if f['description']:
                            line += f"\n  {f['description']}"
                        tooltip_lines.append(line)
                    else:
                        tooltip_lines.append(f"• {f['name']}: —")
                tooltip_lines.append(f"\nAverage: {sum(vals)} ÷ {len(vals)} = {avg:.1f}")
                cost_section_data.append({
                    'avg': avg,
                    'factors': factors_detail,
                    'tooltip': '\n'.join(tooltip_lines)
                })
            else:
                tooltip_lines = [f"• {f['name']}: —" for f in factors_detail]
                tooltip_lines.append('\nNo scores set')
                cost_section_data.append({'avg': None, 'factors': factors_detail, 'tooltip': '\n'.join(tooltip_lines)})

        # For backwards compatibility, extract just the averages
        value_section_avgs = [d['avg'] for d in value_section_data]
        cost_section_avgs = [d['avg'] for d in cost_section_data]

        # Total Value = sum of section averages (not sum of all individual scores)
        value_sum = sum(avg for avg in value_section_avgs if avg is not None)
        # Total Cost = sum of section averages (not sum of all individual scores)
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

        # simple result class for coloring in template
        if result is None:
            result_class = "neutral"
        else:
            result_class = "good" if result >= 1 else "bad"
            
        # Build result tooltip
        if result is not None:
            result_tooltip = f"Value ({value_sum:.1f}) ÷ Cost ({cost_sum:.1f}) = {result:.2f}"
        else:
            result_tooltip = "Cannot calculate (no cost)"

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
            }
        )

    context = {
        "value_sections": value_sections,
        "cost_sections": cost_sections,
        "rows": rows,
        # total columns for the table: Story, Status, per-value-sections, Total Value,
        # per-cost-sections, Total Cost, Result
        "total_cols": 5 + len(value_sections) + len(cost_sections),
        "status_filter": status_filter,
        # Label filter context
        "label_categories": label_filter_ctx['label_categories'],
        "selected_labels": label_filter_ctx['selected_labels'],
        "selected_labels_objects": label_filter_ctx['selected_labels_objects'],
        "labels_param": label_filter_ctx['labels_param'],
    }
    return render(request, "backlog/report.html", context)


def _calculate_story_score(story, value_sections=None, cost_sections=None):
    """Calculate value/cost result for a story (same as report logic).
    
    Score = sum of section averages for value / sum of section averages for cost
    
    Args:
        story: Story instance with prefetched scores/cost_scores
        value_sections: Optional pre-loaded ValueFactorSection queryset
        cost_sections: Optional pre-loaded CostFactorSection queryset
        
    If sections are not provided, they will be loaded from database.
    For batch processing, pass pre-loaded sections to avoid N+1 queries.
    """
    # Get all sections (use provided or load from DB)
    if value_sections is None:
        value_sections = ValueFactorSection.objects.prefetch_related("valuefactors").all()
    if cost_sections is None:
        cost_sections = CostFactorSection.objects.prefetch_related("costfactors").all()
    
    # Build maps of factor id -> score (use prefetched data if available)
    vf_map = {sv.valuefactor_id: sv.answer.score for sv in story.scores.all() if sv.answer}
    cf_map = {sc.costfactor_id: sc.answer.score for sc in story.cost_scores.all() if sc.answer}
    
    # Calculate value section averages and sum them
    value_section_avgs = []
    for vs in value_sections:
        vals = [vf_map[vf.id] for vf in vs.valuefactors.all() if vf.id in vf_map]
        if vals:
            value_section_avgs.append(sum(vals) / len(vals))
    
    # Calculate cost section averages and sum them
    cost_section_avgs = []
    for cs in cost_sections:
        vals = [cf_map[cf.id] for cf in cs.costfactors.all() if cf.id in cf_map]
        if vals:
            cost_section_avgs.append(sum(vals) / len(vals))
    
    total_value = sum(value_section_avgs) if value_section_avgs else 0
    total_cost = sum(cost_section_avgs) if cost_section_avgs else 0
    
    # Calculate result (value / cost), handle division by zero
    if total_cost > 0:
        result = round(total_value / total_cost, 2)
    else:
        result = total_value if total_value > 0 else 0
    
    return {'value': total_value, 'cost': total_cost, 'result': result}
