"""
Helper functions for WoS backlog views.

This module contains utility functions used across multiple view modules:
- History tracking for story changes
- Factor section data building for reports
- Tooltip generation for score breakdowns
"""
from ..models import StoryHistory


def track_story_change(story, field_name, old_value, new_value):
    """Record a change to a story field in the history.
    
    Args:
        story: The Story instance being modified
        field_name: Name of the field that changed
        old_value: Previous value (will be converted to string)
        new_value: New value (will be converted to string)
    """
    old_str = str(old_value) if old_value is not None else ''
    new_str = str(new_value) if new_value is not None else ''
    
    if old_str != new_str:
        StoryHistory.objects.create(
            story=story,
            field_name=field_name,
            old_value=old_str if old_str else None,
            new_value=new_str if new_str else None,
        )


def build_factor_section_data(sections, factor_attr, answers_map, with_tooltips=False):
    """Build section data structure for value or cost factor sections.
    
    This is a helper function to reduce code duplication between value and cost
    factor processing in report_view and other views.
    
    Args:
        sections: QuerySet of ValueFactorSection or CostFactorSection
        factor_attr: Attribute name to access factors ('valuefactors' or 'costfactors')
        answers_map: Dict mapping factor_id -> (score, answer_description) or factor_id -> score
        with_tooltips: Whether to build detailed tooltips (for report view)
        
    Returns:
        List of dicts with section data including averages and optionally tooltips
    """
    section_data = []
    
    for section in sections:
        factors_detail = []
        vals = []
        
        for factor in getattr(section, factor_attr).all():
            score_info = answers_map.get(factor.id)
            
            if score_info is not None:
                # Handle both tuple (score, desc) and plain score formats
                if isinstance(score_info, tuple):
                    sc, answer_desc = score_info
                else:
                    sc, answer_desc = score_info, None
                vals.append(sc)
                factors_detail.append({
                    'name': factor.name,
                    'description': getattr(factor, 'description', ''),
                    'score': sc,
                    'answer_description': answer_desc
                })
            else:
                factors_detail.append({
                    'name': factor.name,
                    'description': getattr(factor, 'description', ''),
                    'score': None,
                    'answer_description': None
                })
        
        if vals:
            avg = sum(vals) / len(vals)
            tooltip = ''
            if with_tooltips:
                tooltip = build_factor_tooltip(factors_detail, sum(vals), len(vals), avg)
            section_data.append({
                'avg': avg,
                'factors': factors_detail,
                'tooltip': tooltip
            })
        else:
            tooltip = ''
            if with_tooltips:
                tooltip_lines = [f"• {f['name']}: —" for f in factors_detail]
                tooltip_lines.append('\nNo scores set')
                tooltip = '\n'.join(tooltip_lines)
            section_data.append({'avg': None, 'factors': factors_detail, 'tooltip': tooltip})
    
    return section_data


def build_factor_tooltip(factors_detail, total, count, avg):
    """Build a multi-line tooltip showing factor breakdown.
    
    Args:
        factors_detail: List of factor dicts with name, score, description, answer_description
        total: Sum of scores
        count: Number of scores
        avg: Calculated average
        
    Returns:
        Multi-line string for tooltip display
    """
    tooltip_lines = []
    for f in factors_detail:
        if f['score'] is not None:
            line = f"• {f['name']}: {f['score']}"
            if f.get('answer_description'):
                line += f" ({f['answer_description']})"
            if f.get('description'):
                line += f"\n  {f['description']}"
            tooltip_lines.append(line)
        else:
            tooltip_lines.append(f"• {f['name']}: —")
    tooltip_lines.append(f"\nAverage: {total} ÷ {count} = {avg:.1f}")
    return '\n'.join(tooltip_lines)


def build_answers_with_undefined(answers_qs):
    """Build answers list with an 'Undefined' option prepended.
    
    Args:
        answers_qs: QuerySet of ValueFactorAnswer or CostFactorAnswer
        
    Returns:
        List with undefined option followed by actual answers
    """
    answers = list(answers_qs.order_by('score'))
    return [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers


def get_label_filter_context(request):
    """Get label filter context data for templates.
    
    Parses the 'labels' GET parameter (comma-separated IDs) and returns
    context data including all categories with their labels and the
    set of selected label IDs.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Dict with:
        - label_categories: List of categories with their labels
        - selected_labels: Set of selected label IDs (as integers)
        - selected_labels_objects: List of selected Label objects for display
        - labels_param: Comma-separated string of selected label IDs for URL params
    """
    from ..models import Label, LabelCategory
    
    # Parse selected labels from URL parameter (format: labels=1,2,3)
    labels_param = request.GET.get('labels', '').strip()
    selected_labels = set()
    if labels_param:
        for lid in labels_param.split(','):
            lid = lid.strip()
            if lid.isdigit():
                selected_labels.add(int(lid))
    
    # Get all categories with their labels, ordered
    categories = LabelCategory.objects.prefetch_related('labels').order_by('name')
    
    label_categories = []
    for cat in categories:
        labels = list(cat.labels.order_by('name'))
        if labels:  # Only include categories that have labels
            label_categories.append({
                'category': cat,
                'labels': labels,
            })
    
    # Get selected label objects for display (with category info)
    selected_labels_objects = []
    if selected_labels:
        selected_labels_objects = list(
            Label.objects.filter(id__in=selected_labels)
            .select_related('category')
            .order_by('category__name', 'name')
        )
    
    return {
        'label_categories': label_categories,
        'selected_labels': selected_labels,
        'selected_labels_objects': selected_labels_objects,
        'labels_param': labels_param,
    }


def apply_label_filter(queryset, selected_labels):
    """Apply label filter to a Story queryset.
    
    Filters stories that have ALL of the selected labels (AND logic).
    Returns distinct results to avoid duplicates.
    
    Args:
        queryset: Story QuerySet to filter
        selected_labels: Set or list of label IDs to filter by
        
    Returns:
        Filtered Story QuerySet
    """
    if selected_labels:
        # AND logic: story must have ALL selected labels
        for label_id in selected_labels:
            queryset = queryset.filter(labels__id=label_id)
        queryset = queryset.distinct()
    return queryset
