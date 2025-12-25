from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib import messages
import json

from .models import (
    Epic,
    Story,
    ValueFactorSection,
    CostFactorSection,
    ValueFactor,
    CostFactor,
    ValueFactorAnswer,
    CostFactorAnswer,
    StoryValueFactorScore,
    StoryCostFactorScore,
    StoryDependency,
    StoryHistory,
)


def track_story_change(story, field_name, old_value, new_value):
    """Record a change to a story field in the history."""
    # Convert values to strings for comparison and storage
    old_str = str(old_value) if old_value is not None else ''
    new_str = str(new_value) if new_value is not None else ''
    
    # Only record if values actually changed
    if old_str != new_str:
        StoryHistory.objects.create(
            story=story,
            field_name=field_name,
            old_value=old_str if old_str else None,
            new_value=new_str if new_str else None,
        )


def overview(request):
    """Overview: show a list of Epics. Clicking an epic should go to the stories page filtered by that epic."""
    # handle epic create/edit/delete/archive from the overview header inline form
    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'create_epic':
            title = request.POST.get('title', '').strip()
            desc = request.POST.get('description', '').strip()
            if title:
                Epic.objects.create(title=title, description=desc)
            return redirect(request.path)
        if action == 'edit_epic':
            eid = request.POST.get('epic_id')
            epic = get_object_or_404(Epic, pk=eid)
            epic.title = request.POST.get('title', epic.title)
            epic.description = request.POST.get('description', epic.description)
            epic.save()
            return redirect(request.path)
        if action == 'delete_epic':
            eid = request.POST.get('epic_id')
            epic = get_object_or_404(Epic, pk=eid)
            epic.delete()
            return redirect(request.path)
        if action == 'archive_epic':
            eid = request.POST.get('epic_id')
            epic = get_object_or_404(Epic, pk=eid)
            epic.archived = True
            epic.save()
            # Also archive all child stories
            epic.stories.update(archived=True)
            return redirect(request.path)
        if action == 'unarchive_epic':
            eid = request.POST.get('epic_id')
            epic = get_object_or_404(Epic, pk=eid)
            epic.archived = False
            epic.save()
            return redirect(request.path)

    # Filtering & sorting
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'title')
    order = request.GET.get('order', 'asc')
    show_archived = request.GET.get('archived', '') == '1'

    epics_qs = Epic.objects.prefetch_related('stories').annotate(story_count=Count('stories'))
    
    # Filter by archived status
    epics_qs = epics_qs.filter(archived=show_archived)
    
    if q:
        epics_qs = epics_qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    # sort mapping
    sort_map = {
        'title': 'title',
        'created': 'created_at',
        'updated': 'updated_at',
        'stories': 'story_count',
    }
    sort_field = sort_map.get(sort, 'title')
    if order == 'desc':
        sort_field = '-' + sort_field

    epics_qs = epics_qs.order_by(sort_field)

    epics = []
    for e in epics_qs:
        # Truncate description to 100 chars
        desc = e.description or ''
        if len(desc) > 100:
            desc = desc[:100] + '…'
        # Count unfinished stories (not 'done' status)
        unfinished_count = sum(1 for s in e.stories.filter(archived=False) if s.computed_status != 'done')
        epics.append({'epic': e, 'description': desc, 'unfinished_count': unfinished_count})

    context = {
        'epics': epics,
        'q': q,
        'sort': sort,
        'order': order,
        'show_archived': show_archived,
    }
    return render(request, 'backlog/overview.html', context)


def refine_story(request, pk):
    """Separate page to refine a story: edit target and workitems."""
    story = get_object_or_404(Story, pk=pk)
    epics = Epic.objects.order_by("title")
    # load factor sections for scoring UI
    value_sections = ValueFactorSection.objects.prefetch_related("valuefactors__answers").order_by("name")
    cost_sections = CostFactorSection.objects.prefetch_related("costfactors__answers").order_by("name")

    # build initial selected answer maps
    vf_initial = {sv.valuefactor_id: sv.answer_id for sv in story.scores.all()}
    cf_initial = {sv.costfactor_id: sv.answer_id for sv in story.cost_scores.all()}

    # Build structured data for templates: sections -> factors -> answers + selected id
    value_sections_data = []
    for vs in value_sections:
        vf_list = []
        for vf in vs.valuefactors.all():
            answers = list(vf.answers.order_by('score'))
            # Add undefined option
            answers_with_undefined = [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers
            selected = vf_initial.get(vf.id, '')
            vf_list.append({'vf': vf, 'answers': answers_with_undefined, 'selected': selected})
        value_sections_data.append({'section': vs, 'valuefactors': vf_list})

    cost_sections_data = []
    for cs in cost_sections:
        cf_list = []
        for cf in cs.costfactors.all():
            answers = list(cf.answers.order_by('score'))
            # Add undefined option
            answers_with_undefined = [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers
            selected = cf_initial.get(cf.id, '')
            cf_list.append({'cf': cf, 'answers': answers_with_undefined, 'selected': selected})
        cost_sections_data.append({'section': cs, 'costfactors': cf_list})
    
    # Get current dependencies
    dependencies = story.dependencies.select_related('depends_on__epic').all()
    
    # Get stories that depend on this story (dependents)
    dependents = story.dependents.select_related('story__epic').all()
    
    # Get available stories for dependency picker (grouped by epic)
    # First: stories in same epic (excluding self), then other epics
    same_epic_stories = Story.objects.filter(epic=story.epic).exclude(pk=story.pk).order_by('title')
    other_stories = Story.objects.exclude(epic=story.epic).exclude(pk=story.pk).select_related('epic').order_by('epic__title', 'title')
    
    # Group other stories by epic
    other_epics_stories = {}
    for s in other_stories:
        if s.epic.id not in other_epics_stories:
            other_epics_stories[s.epic.id] = {'epic': s.epic, 'stories': []}
        other_epics_stories[s.epic.id]['stories'].append(s)
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        # Handle dependency actions
        if action == "add_dependency":
            dep_story_id = request.POST.get("dependency_story_id")
            if dep_story_id:
                dep_story = get_object_or_404(Story, pk=dep_story_id)
                if dep_story.pk != story.pk:
                    created = StoryDependency.objects.get_or_create(story=story, depends_on=dep_story)[1]
                    if created:
                        track_story_change(story, 'Dependency added', None, dep_story.title)
            return redirect(request.path)
        
        if action == "remove_dependency":
            dep_id = request.POST.get("dependency_id")
            if dep_id:
                dep = StoryDependency.objects.filter(pk=dep_id, story=story).first()
                if dep:
                    track_story_change(story, 'Dependency removed', dep.depends_on.title, None)
                    dep.delete()
            return redirect(request.path)
        
        if action == "archive_story":
            track_story_change(story, 'Archived', 'No', 'Yes')
            story.archived = True
            story.save()
            return redirect('backlog:stories')
        
        if action == "unarchive_story":
            track_story_change(story, 'Archived', 'Yes', 'No')
            story.archived = False
            story.save()
            return redirect(request.path)
        
        if action == "toggle_review":
            old_val = 'Yes' if story.review_required else 'No'
            story.review_required = not story.review_required
            new_val = 'Yes' if story.review_required else 'No'
            track_story_change(story, 'Review required', old_val, new_val)
            story.save()
            return redirect(request.path)
        
        # Check if remove_blocked button was clicked
        if request.POST.get("remove_blocked"):
            track_story_change(story, 'Blocked', story.blocked, '')
            story.blocked = ""
            story.save()
            return redirect(request.path)
        
        # Store old values for tracking
        old_title = story.title
        old_epic = story.epic
        old_goal = story.goal
        old_workitems = story.workitems
        old_blocked = story.blocked
        
        # allow updating title and epic here (refinement)
        title = request.POST.get("title")
        if title is not None:
            story.title = title.strip()

        epic_pk = request.POST.get("epic_id")
        if epic_pk:
            story.epic = get_object_or_404(Epic, pk=epic_pk)

        story.goal = request.POST.get("goal", story.goal)
        story.workitems = request.POST.get("workitems", story.workitems)
        
        # Handle blocked field
        story.blocked = request.POST.get("blocked", "").strip()
        
        # Track text field changes
        track_story_change(story, 'Title', old_title, story.title)
        if old_epic != story.epic:
            track_story_change(story, 'Epic', old_epic.title, story.epic.title)
        track_story_change(story, 'Goal', old_goal, story.goal)
        track_story_change(story, 'Work items', old_workitems, story.workitems)
        track_story_change(story, 'Blocked', old_blocked, story.blocked)
        
        story.save()
        # Persist selected answers for each ValueFactor submitted from the form
        for vf in ValueFactor.objects.all():
            field_name = f"vf_{vf.id}"
            if field_name not in request.POST:
                continue
            ans_value = request.POST.get(field_name, '').strip()
            
            # Get current score for tracking
            current_score = StoryValueFactorScore.objects.filter(story=story, valuefactor=vf).first()
            old_score_str = f"{current_score.answer.score}" if current_score else 'Undefined'
            
            if not ans_value or ans_value == '':
                # Undefined selected - delete the score
                if current_score:
                    track_story_change(story, f'Value: {vf.name}', old_score_str, 'Undefined')
                StoryValueFactorScore.objects.filter(story=story, valuefactor=vf).delete()
                continue
            try:
                ans_id = int(ans_value)
                answer = ValueFactorAnswer.objects.filter(id=ans_id, valuefactor=vf).first()
            except Exception:
                answer = None
            if answer:
                new_score_str = f"{answer.score}"
                if old_score_str != new_score_str:
                    track_story_change(story, f'Value: {vf.name}', old_score_str, new_score_str)
                StoryValueFactorScore.objects.update_or_create(
                    story=story, valuefactor=vf, defaults={"answer": answer}
                )

        # Persist selected answers for each CostFactor
        for cf in CostFactor.objects.all():
            field_name = f"cf_{cf.id}"
            if field_name not in request.POST:
                continue
            ans_value = request.POST.get(field_name, '').strip()
            
            # Get current score for tracking
            current_score = StoryCostFactorScore.objects.filter(story=story, costfactor=cf).first()
            old_score_str = f"{current_score.answer.score}" if current_score else 'Undefined'
            
            if not ans_value or ans_value == '':
                # Undefined selected - delete the score
                if current_score:
                    track_story_change(story, f'Cost: {cf.name}', old_score_str, 'Undefined')
                StoryCostFactorScore.objects.filter(story=story, costfactor=cf).delete()
                continue
            try:
                ans_id = int(ans_value)
                answer = CostFactorAnswer.objects.filter(id=ans_id, costfactor=cf).first()
            except Exception:
                answer = None
            if answer:
                new_score_str = f"{answer.score}"
                if old_score_str != new_score_str:
                    track_story_change(story, f'Cost: {cf.name}', old_score_str, new_score_str)
                StoryCostFactorScore.objects.update_or_create(
                    story=story, costfactor=cf, defaults={"answer": answer}
                )
        messages.success(request, f'✅ Story "{story.title}" has been updated successfully.')
        return redirect('backlog:refine_story', pk=story.pk)

    # Get history for this story
    history = story.history.all()[:50]  # Limit to last 50 entries

    return render(
        request,
        "backlog/refine.html",
        {
            "story": story,
            "epics": epics,
            "value_sections": value_sections_data,
            "cost_sections": cost_sections_data,
            "dependencies": dependencies,
            "dependents": dependents,
            "same_epic_stories": same_epic_stories,
            "other_epics_stories": list(other_epics_stories.values()),
            "history": history,
        },
    )


def create_story_refine(request):
    """Show the refine template to create a new story.

    On GET: render the same `refine.html` but with an unsaved Story-like object.
    On POST: create the story and redirect to overview.
    """
    epics = Epic.objects.order_by("title")
    # factor sections for scoring UI (useful for preselecting defaults)
    value_sections = ValueFactorSection.objects.prefetch_related("valuefactors__answers").order_by("name")
    cost_sections = CostFactorSection.objects.prefetch_related("costfactors__answers").order_by("name")

    # build defaults structure for template
    value_sections_data = []
    for vs in value_sections:
        vf_list = []
        for vf in vs.valuefactors.all():
            answers = list(vf.answers.order_by('score'))
            # Add undefined option (default for new stories)
            answers_with_undefined = [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers
            selected = ''  # Default to undefined for new stories
            vf_list.append({'vf': vf, 'answers': answers_with_undefined, 'selected': selected})
        value_sections_data.append({'section': vs, 'valuefactors': vf_list})

    cost_sections_data = []
    for cs in cost_sections:
        cf_list = []
        for cf in cs.costfactors.all():
            answers = list(cf.answers.order_by('score'))
            # Add undefined option (default for new stories)
            answers_with_undefined = [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers
            selected = ''  # Default to undefined for new stories
            cf_list.append({'cf': cf, 'answers': answers_with_undefined, 'selected': selected})
        cost_sections_data.append({'section': cs, 'costfactors': cf_list})
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        epic_pk = request.POST.get("epic_id")
        goal = request.POST.get("goal", "").strip()
        workitems = request.POST.get("workitems", "").strip()
        
        if title and epic_pk:
            epic = get_object_or_404(Epic, pk=epic_pk)
            
            # Create story with all fields
            story = Story.objects.create(
                epic=epic,
                title=title,
                goal=goal,
                workitems=workitems
            )
            
            # Track story creation
            StoryHistory.objects.create(
                story=story,
                field_name='Story created',
                old_value=None,
                new_value=f'Created in epic: {epic.title}'
            )
            
            # Handle blocked field (started/finished are read-only and not set on creation)
            story.blocked = request.POST.get("blocked", "").strip()
            story.save()
            
            # Persist any selected answers that were submitted on creation
            for vf in ValueFactor.objects.all():
                field_name = f"vf_{vf.id}"
                if field_name not in request.POST:
                    continue
                ans_value = request.POST.get(field_name, '').strip()
                if not ans_value or ans_value == '':
                    # Undefined selected - delete the score (if it exists from signal)
                    StoryValueFactorScore.objects.filter(story=story, valuefactor=vf).delete()
                    continue
                try:
                    ans_id = int(ans_value)
                    answer = ValueFactorAnswer.objects.filter(id=ans_id, valuefactor=vf).first()
                except Exception:
                    answer = None
                if answer:
                    StoryValueFactorScore.objects.update_or_create(
                        story=story, valuefactor=vf, defaults={"answer": answer}
                    )

            for cf in CostFactor.objects.all():
                field_name = f"cf_{cf.id}"
                if field_name not in request.POST:
                    continue
                ans_value = request.POST.get(field_name, '').strip()
                if not ans_value or ans_value == '':
                    # Undefined selected - delete the score (if it exists from signal)
                    StoryCostFactorScore.objects.filter(story=story, costfactor=cf).delete()
                    continue
                try:
                    ans_id = int(ans_value)
                    answer = CostFactorAnswer.objects.filter(id=ans_id, costfactor=cf).first()
                except Exception:
                    answer = None
                if answer:
                    StoryCostFactorScore.objects.update_or_create(
                        story=story, costfactor=cf, defaults={"answer": answer}
                    )

            messages.success(request, f'✅ Story "{story.title}" has been created successfully.')
            return redirect('backlog:refine_story', pk=story.pk)
        # if validation fails, fall through to re-render the form with epics

    # create a lightweight story-like object for the template
    class _S:
        def __init__(self):
            self.id = None
            self.title = ""
            self.target = ""
            self.workitems = ""
            self.description = ""
            self.planned = None
            self.started = None
            self.finished = None
            self.blocked = ""
            self.epic = None

    story = _S()
    return render(
        request,
        "backlog/refine.html",
        {
            "story": story,
            "epics": epics,
            "value_sections": value_sections_data,
            "cost_sections": cost_sections_data,
        },
    )


def story_list(request):
    """List stories (optionally filtered by epic via ?epic=ID). Supports search and sorting."""
    # Handle POST actions for archiving
    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'archive_story':
            sid = request.POST.get('story_id')
            story = get_object_or_404(Story, pk=sid)
            story.archived = True
            story.save()
            return redirect(request.get_full_path())
        if action == 'unarchive_story':
            sid = request.POST.get('story_id')
            story = get_object_or_404(Story, pk=sid)
            story.archived = False
            story.save()
            return redirect(request.get_full_path())
        if action == 'toggle_review':
            sid = request.POST.get('story_id')
            story = get_object_or_404(Story, pk=sid)
            story.review_required = not story.review_required
            story.save()
            return redirect(request.get_full_path())
        if action == 'delete_story':
            sid = request.POST.get('story_id')
            story = get_object_or_404(Story, pk=sid)
            story.delete()
            return redirect(request.get_full_path())
    
    epic_id = request.GET.get('epic')
    status_filter = request.GET.get('status', '').strip()
    review_filter = request.GET.get('review', '').strip()
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'epic')
    order = request.GET.get('order', 'asc')
    show_archived = request.GET.get('archived', '') == '1'

    # provide list of epics for the epic filter dropdown (non-archived only for filter)
    all_epics = Epic.objects.filter(archived=False).order_by('title')
    # provide list of possible statuses
    all_statuses = ['idea', 'ready', 'planned', 'started', 'done', 'blocked']

    qs = Story.objects.select_related('epic').prefetch_related('scores', 'cost_scores')
    
    # Filter by archived status
    qs = qs.filter(archived=show_archived)
    
    if epic_id:
        qs = qs.filter(epic_id=epic_id)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(goal__icontains=q) | Q(workitems__icontains=q))

    sort_map = {
        'title': 'title',
        'epic': 'epic__title',
        'created': 'created_at',
        'status': 'status',
    }
    sort_field = sort_map.get(sort, 'epic__title')
    if order == 'desc':
        sort_field = '-' + sort_field

    qs = qs.order_by(sort_field)
    stories = list(qs)
    
    # Filter by computed_status (must be done after fetching since it's a property)
    if status_filter:
        stories = [s for s in stories if s.computed_status == status_filter]
    
    # Filter by review_required
    if review_filter == 'yes':
        stories = [s for s in stories if s.review_required]
    elif review_filter == 'no':
        stories = [s for s in stories if not s.review_required]
    
    # Sort by status if requested (must be done after fetching since it's a property)
    if sort == 'status':
        stories.sort(key=lambda s: s.computed_status, reverse=(order == 'desc'))
    
    # Get all value and cost factors for completeness check
    all_value_factors = list(ValueFactor.objects.all())
    all_cost_factors = list(CostFactor.objects.all())
    
    # Add completeness info to each story
    story_data = []
    for s in stories:
        # Check if all details are filled
        has_title = bool(s.title and s.title.strip())
        has_goal = bool(s.goal and s.goal.strip())
        has_workitems = bool(s.workitems and s.workitems.strip())
        details_complete = has_title and has_goal and has_workitems
        
        # Check if all scores are set
        story_vf_ids = set(score.valuefactor_id for score in s.scores.all())
        story_cf_ids = set(score.costfactor_id for score in s.cost_scores.all())
        all_vf_ids = set(vf.id for vf in all_value_factors)
        all_cf_ids = set(cf.id for cf in all_cost_factors)
        scores_complete = (story_vf_ids >= all_vf_ids) and (story_cf_ids >= all_cf_ids)
        
        story_data.append({
            'story': s,
            'details_complete': details_complete,
            'scores_complete': scores_complete,
        })
    
    context = {
        'stories': story_data,
        'q': q,
        'sort': sort,
        'order': order,
        'epic_id': epic_id,
        'status_filter': status_filter,
        'review_filter': review_filter,
        'all_epics': all_epics,
        'all_statuses': all_statuses,
        'show_archived': show_archived,
    }
    return render(request, 'backlog/stories.html', context)


def report_view(request):
    # Build report: per-section averages for value and cost factors, per-story totals and ratio
    epic_id = request.GET.get('epic')
    status_filter = request.GET.get('status', '')
    all_epics = Epic.objects.filter(archived=False).order_by('title')
    
    value_sections = list(
        ValueFactorSection.objects.prefetch_related("valuefactors").order_by("name")
    )
    cost_sections = list(
        CostFactorSection.objects.prefetch_related("costfactors").order_by("name")
    )

    stories_qs = (
        Story.objects.filter(archived=False).select_related("epic").prefetch_related("scores__answer", "cost_scores__answer").order_by(
            "epic__title",
            "title",
        )
    )
    
    if epic_id:
        stories_qs = stories_qs.filter(epic_id=epic_id)
    
    # Status filtering requires post-processing since computed_status is a property
    if status_filter:
        stories_qs = [s for s in stories_qs if s.computed_status == status_filter]
    else:
        stories_qs = list(stories_qs)

    rows = []
    for s in stories_qs:
        # maps of factor id -> numeric score
        vf_map = {sv.valuefactor_id: sv.answer.score for sv in s.scores.all()}
        cf_map = {sv.costfactor_id: sv.answer.score for sv in s.cost_scores.all()}

        # per-value-section averages (ordered to match value_sections)
        value_section_avgs = []
        for vs in value_sections:
            vals = []
            for vf in vs.valuefactors.all():
                sc = vf_map.get(vf.id)
                if sc is not None:
                    vals.append(sc)
            if vals:
                value_section_avgs.append(sum(vals) / len(vals))
            else:
                value_section_avgs.append(None)

        # per-cost-section averages (ordered to match cost_sections)
        cost_section_avgs = []
        for cs in cost_sections:
            vals = []
            for cf in cs.costfactors.all():
                sc = cf_map.get(cf.id)
                if sc is not None:
                    vals.append(sc)
            if vals:
                cost_section_avgs.append(sum(vals) / len(vals))
            else:
                cost_section_avgs.append(None)

        value_sum = sum(vf_map.values()) if vf_map else 0
        cost_sum = sum(cf_map.values()) if cf_map else 0
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

        rows.append(
            {
                "story": s,
                "value_section_avgs": value_section_avgs,
                "cost_section_avgs": cost_section_avgs,
                "value_sum": value_sum,
                "cost_sum": cost_sum,
                "result": result,
                "result_class": result_class,
            }
        )

    context = {
        "value_sections": value_sections,
        "cost_sections": cost_sections,
        "rows": rows,
        # total columns for the table: Epic, Story, Status, per-value-sections, Total Value,
        # per-cost-sections, Total Cost, Result
        "total_cols": 6 + len(value_sections) + len(cost_sections),
        "all_epics": all_epics,
        "epic_id": epic_id,
        "status_filter": status_filter,
    }
    return render(request, "backlog/report.html", context)


def _calculate_story_score(story):
    """Calculate value/cost result for a story (same as report logic)."""
    # Sum value scores
    total_value = 0
    for sv in story.scores.select_related('answer').all():
        total_value += sv.answer.score if sv.answer else 0
    
    # Sum cost scores
    total_cost = 0
    for sc in story.cost_scores.select_related('answer').all():
        total_cost += sc.answer.score if sc.answer else 0
    
    # Calculate result (value / cost), handle division by zero
    if total_cost > 0:
        result = round(total_value / total_cost, 2)
    else:
        result = total_value if total_value > 0 else 0
    
    return {'value': total_value, 'cost': total_cost, 'result': result}


def kanban_view(request):
    """Kanban board with columns grouped by computed status, score result, and sorting."""
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


def health(request):
    """Simple health check endpoint.

    Returns 200 OK with JSON. Attempts a trivial DB query to ensure connectivity.
    """
    try:
        _ = Story.objects.exists()
        return JsonResponse({'status': 'ok'}, status=200)
    except Exception as e:
        return JsonResponse({'status': 'error', 'detail': str(e)}, status=500)


def create_epic(request):
    """Server-side page to create a new Epic. GET shows a small form, POST creates and redirects to overview."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            Epic.objects.create(title=title, description=description)
            return redirect('backlog:index')
        # if invalid, fall through and re-render the form with an error
    return render(request, 'backlog/create_epic.html', {})


def edit_epic(request, pk):
    """Edit an existing Epic with consistent look and feel."""
    epic = get_object_or_404(Epic, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            epic.title = title
            epic.description = description
            epic.save()
            return redirect('backlog:index')
        # fall through and show form with current values
    return render(request, 'backlog/edit_epic.html', {'epic': epic})


def wbs_view(request):
    """Work Breakdown Structure - visual overview of stories and their dependencies."""
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
        cost_sum = sum(cs.answer.score for cs in story.cost_scores.all())
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