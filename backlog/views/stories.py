"""
Story views for WoS backlog application.

Handles story CRUD and refinement:
- refine_story: Full story editing with scores, dependencies, history
- create_story_refine: Create new story via refine interface
- story_list: List/filter/sort stories
- bulk_action: Handle bulk actions on multiple stories
"""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import (
    CostFactor,
    CostFactorAnswer,
    CostFactorSection,
    Label,
    LabelCategory,
    Story,
    StoryCostFactorScore,
    StoryDependency,
    StoryHistory,
    StoryValueFactorScore,
    ValueFactor,
    ValueFactorAnswer,
    ValueFactorSection,
)
from .helpers import apply_label_filter, get_label_filter_context, track_story_change


def refine_story(request, pk):
    """Refine an existing story with full editing capabilities.
    
    This view allows editing:
    - Basic info: title, goal, workitems
    - Value/cost factor scores
    - Dependencies on other stories
    - Archive/unarchive and review flags
    
    Also displays story history and dependent stories.
    """
    story = get_object_or_404(Story, pk=pk)
    # load factor sections for scoring UI
    value_sections = ValueFactorSection.objects.prefetch_related("valuefactors__answers").order_by("name")
    cost_sections = CostFactorSection.objects.prefetch_related("costfactors__answers").order_by("name")

    # build initial selected answer maps (answer_id or None for undefined)
    vf_initial = {sv.valuefactor_id: sv.answer_id for sv in story.scores.all()}
    cf_initial = {sv.costfactor_id: sv.answer_id for sv in story.cost_scores.all()}

    # Build structured data for templates: sections -> factors -> answers + selected id
    value_sections_data = []
    for vs in value_sections:
        vf_list = []
        for vf in vs.valuefactors.all():
            answers = list(vf.answers.order_by('score'))
            # Add undefined option (empty string id to distinguish from answer_id=None)
            answers_with_undefined = [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers
            # Get selected answer_id; None or missing means undefined (select the '' option)
            selected = vf_initial.get(vf.id)
            if selected is None:
                selected = ''  # Mark as undefined
            vf_list.append({'vf': vf, 'answers': answers_with_undefined, 'selected': selected})
        value_sections_data.append({'section': vs, 'valuefactors': vf_list})

    cost_sections_data = []
    for cs in cost_sections:
        cf_list = []
        for cf in cs.costfactors.all():
            answers = list(cf.answers.order_by('score'))
            # Add undefined option
            answers_with_undefined = [{'id': '', 'score': '—', 'description': 'Undefined'}] + answers
            # Get selected answer_id; None or missing means undefined (select the '' option)
            selected = cf_initial.get(cf.id)
            if selected is None:
                selected = ''  # Mark as undefined
            cf_list.append({'cf': cf, 'answers': answers_with_undefined, 'selected': selected})
        cost_sections_data.append({'section': cs, 'costfactors': cf_list})
    
    # Get current dependencies
    dependencies = story.dependencies.select_related('depends_on').all()
    
    # Get stories that depend on this story (dependents)
    dependents = story.dependents.select_related('story').all()
    
    # Get available stories for dependency picker
    other_stories = Story.objects.exclude(pk=story.pk).order_by('title')
    
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
        old_goal = story.goal
        old_workitems = story.workitems
        old_blocked = story.blocked
        
        # allow updating title here (refinement)
        title = request.POST.get("title")
        if title is not None:
            story.title = title.strip()

        story.goal = request.POST.get("goal", story.goal)
        story.workitems = request.POST.get("workitems", story.workitems)
        
        # Handle blocked field
        story.blocked = request.POST.get("blocked", "").strip()
        
        # Track text field changes
        track_story_change(story, 'Title', old_title, story.title)
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
            old_score_str = f"{current_score.answer.score}" if current_score and current_score.answer else 'Undefined'
            
            if not ans_value or ans_value == '':
                # Undefined selected - set answer to None
                if current_score and current_score.answer:
                    track_story_change(story, f'Value: {vf.name}', old_score_str, 'Undefined')
                    current_score.answer = None
                    current_score.save()
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
            old_score_str = f"{current_score.answer.score}" if current_score and current_score.answer else 'Undefined'
            
            if not ans_value or ans_value == '':
                # Undefined selected - set answer to None
                if current_score and current_score.answer:
                    track_story_change(story, f'Cost: {cf.name}', old_score_str, 'Undefined')
                    current_score.answer = None
                    current_score.save()
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
        
        # Handle labels
        old_labels = set(story.labels.values_list('id', flat=True))
        new_label_ids = request.POST.getlist('labels')
        new_labels = set()
        for lid in new_label_ids:
            try:
                new_labels.add(int(lid))
            except (ValueError, TypeError):
                pass
        
        if old_labels != new_labels:
            # Track label changes
            old_label_names = sorted([l.name for l in Label.objects.filter(id__in=old_labels)])
            new_label_names = sorted([l.name for l in Label.objects.filter(id__in=new_labels)])
            track_story_change(
                story, 
                'Labels', 
                ', '.join(old_label_names) or '(none)',
                ', '.join(new_label_names) or '(none)'
            )
            story.labels.set(new_labels)
        
        messages.success(request, f'✅ Story "{story.title}" has been updated successfully.')
        # Redirect to next URL if provided, otherwise to story detail
        next_url = request.POST.get('next', '').strip()
        if next_url:
            return redirect(next_url)
        return redirect('backlog:story_detail', pk=story.pk)

    # Get history for this story
    history = story.history.all()[:50]  # Limit to last 50 entries
    
    # Get all labels grouped by category
    label_categories = LabelCategory.objects.prefetch_related('labels').order_by('name')
    story_labels = set(story.labels.values_list('id', flat=True))
    
    # Get next URL from query param for back link
    next_url = request.GET.get('next', '').strip()
    back_url = reverse('backlog:stories')

    return render(
        request,
        "backlog/refine.html",
        {
            "story": story,
            "value_sections": value_sections_data,
            "cost_sections": cost_sections_data,
            "dependencies": dependencies,
            "dependents": dependents,
            "other_stories": other_stories,
            "history": history,
            "label_categories": label_categories,
            "story_labels": story_labels,
            "next_url": next_url,
            "back_url": back_url,
        },
    )


def create_story_refine(request):
    """Show the refine template to create a new story.

    On GET: render the same `refine.html` but with an unsaved Story-like object.
    On POST: create the story and redirect to overview.
    """
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
        goal = request.POST.get("goal", "").strip()
        workitems = request.POST.get("workitems", "").strip()
        
        if title:
            # Create story with all fields
            story = Story.objects.create(
                title=title,
                goal=goal,
                workitems=workitems
            )
            
            # Track story creation
            StoryHistory.objects.create(
                story=story,
                field_name='Story created',
                old_value=None,
                new_value=f'Created: {title}'
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

            # Handle labels on creation
            new_label_ids = request.POST.getlist('labels')
            if new_label_ids:
                label_ids = []
                for lid in new_label_ids:
                    try:
                        label_ids.append(int(lid))
                    except (ValueError, TypeError):
                        pass
                if label_ids:
                    story.labels.set(label_ids)
                    label_names = sorted([l.name for l in Label.objects.filter(id__in=label_ids)])
                    StoryHistory.objects.create(
                        story=story,
                        field_name='Labels',
                        old_value='(none)',
                        new_value=', '.join(label_names)
                    )

            messages.success(request, f'✅ Story "{story.title}" has been created successfully.')
            # Redirect to next URL if provided, otherwise to story detail
            next_url = request.POST.get('next', '').strip()
            if next_url:
                return redirect(next_url)
            return redirect('backlog:story_detail', pk=story.pk)
        else:
            # Validation failed - show error and preserve input
            errors = []
            if not title:
                errors.append('Title is required')
            messages.error(request, '❌ ' + ', '.join(errors) + '.')
            
            # Preserve the submitted values
            class _S:
                def __init__(self):
                    self.id = None
                    self.title = request.POST.get("title", "").strip()
                    self.goal = request.POST.get("goal", "").strip()
                    self.workitems = request.POST.get("workitems", "").strip()
                    self.blocked = request.POST.get("blocked", "").strip()
                    self.planned = None
                    self.started = None
                    self.finished = None
            
            story = _S()
            # Preserve next_url on validation error
            next_url = request.POST.get('next', '').strip()
            back_url = reverse('backlog:stories')
            # Get labels for the form, preserving selection
            label_categories = LabelCategory.objects.prefetch_related('labels').order_by('name')
            story_labels = set()
            for lid in request.POST.getlist('labels'):
                try:
                    story_labels.add(int(lid))
                except (ValueError, TypeError):
                    pass
            return render(
                request,
                "backlog/refine.html",
                {
                    "story": story,
                    "value_sections": value_sections_data,
                    "cost_sections": cost_sections_data,
                    "label_categories": label_categories,
                    "story_labels": story_labels,
                    "next_url": next_url,
                    "back_url": back_url,
                },
            )

    # GET request - create a lightweight story-like object for the template
    class _S:
        def __init__(self):
            self.id = None
            self.title = ""
            self.goal = ""
            self.workitems = ""
            self.blocked = ""
            self.planned = None
            self.started = None
            self.finished = None

    story = _S()
    
    # Get next URL from query param for back link
    next_url = request.GET.get('next', '').strip()
    back_url = reverse('backlog:stories')
    
    # Get all labels grouped by category
    label_categories = LabelCategory.objects.prefetch_related('labels').order_by('name')
    story_labels = set()  # No labels selected for new story
    
    return render(
        request,
        "backlog/refine.html",
        {
            "story": story,
            "value_sections": value_sections_data,
            "cost_sections": cost_sections_data,
            "label_categories": label_categories,
            "story_labels": story_labels,
            "next_url": next_url,
            "back_url": back_url,
        },
    )


def story_list(request):
    """List all stories with filtering and sorting capabilities.
    
    Supports:
    - Filter by epic, computed status, review required flag
    - Search by title, goal, or workitems
    - Sort by title, epic, created date, or status
    - Toggle between active and archived stories
    - Inline archive/unarchive/delete actions
    """
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
    
    # Get label filter context
    label_filter_ctx = get_label_filter_context(request)
    
    status_filter = request.GET.get('status', '').strip()
    review_filter = request.GET.get('review', '').strip()
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'title')
    order = request.GET.get('order', 'asc')
    show_archived = request.GET.get('archived', '') == '1'

    # provide list of possible statuses
    all_statuses = ['idea', 'ready', 'planned', 'started', 'done', 'blocked']

    qs = Story.objects.prefetch_related('scores', 'cost_scores', 'labels__category')
    
    # Filter by archived status
    qs = qs.filter(archived=show_archived)
    
    # Filter by labels (multi-select with OR logic)
    qs = apply_label_filter(qs, label_filter_ctx['selected_labels'])
    
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(goal__icontains=q) | Q(workitems__icontains=q))

    sort_map = {
        'title': 'title',
        'created': 'created_at',
        'status': 'status',
    }
    sort_field = sort_map.get(sort, 'title')
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
        'status_filter': status_filter,
        'review_filter': review_filter,
        'all_statuses': all_statuses,
        'show_archived': show_archived,
        # Label filter context
        'label_categories': label_filter_ctx['label_categories'],
        'selected_labels': label_filter_ctx['selected_labels'],
        'selected_labels_objects': label_filter_ctx['selected_labels_objects'],
        'labels_param': label_filter_ctx['labels_param'],
        # All label categories for bulk add labels modal
        'all_label_categories': LabelCategory.objects.prefetch_related('labels').order_by('name'),
    }
    return render(request, 'backlog/stories.html', context)


@require_POST
def bulk_action(request):
    """Handle bulk actions on multiple stories.
    
    Supported actions:
    - add_labels: Add labels to selected stories
    - set_review: Set review_required flag on selected stories
    - clear_review: Clear review_required flag on selected stories
    - set_blocked: Set blocked reason on selected stories
    - archive: Archive selected stories
    - unarchive: Unarchive selected stories
    - delete: Delete selected stories
    """
    action = request.POST.get('action', '')
    story_ids_str = request.POST.get('story_ids', '')
    next_url = request.POST.get('next', reverse('backlog:stories'))
    
    # Parse story IDs
    story_ids = []
    for sid in story_ids_str.split(','):
        try:
            story_ids.append(int(sid.strip()))
        except (ValueError, TypeError):
            pass
    
    if not story_ids:
        messages.warning(request, '⚠️ No stories selected.')
        return redirect(next_url)
    
    stories = Story.objects.filter(id__in=story_ids)
    count = stories.count()
    
    if count == 0:
        messages.warning(request, '⚠️ No valid stories found.')
        return redirect(next_url)
    
    if action == 'add_labels':
        label_ids_str = request.POST.get('label_ids', '')
        label_ids = []
        for lid in label_ids_str.split(','):
            try:
                label_ids.append(int(lid.strip()))
            except (ValueError, TypeError):
                pass
        
        if label_ids:
            labels = Label.objects.filter(id__in=label_ids)
            label_names = ', '.join(sorted([l.name for l in labels]))
            for story in stories:
                # Add labels (don't remove existing)
                current_labels = set(story.labels.values_list('id', flat=True))
                new_labels = set(label_ids) - current_labels
                if new_labels:
                    story.labels.add(*new_labels)
                    StoryHistory.objects.create(
                        story=story,
                        field_name='Labels',
                        old_value='(added)',
                        new_value=label_names
                    )
            messages.success(request, f'🏷️ Added labels to {count} stories.')
        else:
            messages.warning(request, '⚠️ No labels selected.')
    
    elif action == 'set_review':
        stories.update(review_required=True)
        messages.success(request, f'🚩 Set review required on {count} stories.')
    
    elif action == 'clear_review':
        stories.update(review_required=False)
        messages.success(request, f'✅ Cleared review flag from {count} stories.')
    
    elif action == 'set_blocked':
        blocked_reason = request.POST.get('blocked_reason', '').strip()
        if blocked_reason:
            for story in stories:
                old_blocked = story.blocked
                story.blocked = blocked_reason
                story.save()
                if old_blocked != blocked_reason:
                    StoryHistory.objects.create(
                        story=story,
                        field_name='Blocked',
                        old_value=old_blocked or '(not blocked)',
                        new_value=blocked_reason
                    )
            messages.success(request, f'🚫 Marked {count} stories as blocked.')
        else:
            messages.warning(request, '⚠️ No blocked reason provided.')
    
    elif action == 'archive':
        stories.update(archived=True)
        messages.success(request, f'📦 Archived {count} stories.')
    
    elif action == 'unarchive':
        stories.update(archived=False)
        messages.success(request, f'📤 Unarchived {count} stories.')
    
    elif action == 'delete':
        stories.delete()
        messages.success(request, f'🗑️ Deleted {count} stories.')
    
    else:
        messages.warning(request, f'⚠️ Unknown action: {action}')
    
    return redirect(next_url)


def create_label(request):
    """AJAX endpoint to create a new label.
    
    Expects JSON body with:
    - category_id: ID of the LabelCategory
    - name: Name for the new label
    
    Returns JSON with:
    - success: True/False
    - label_id: ID of the created label (on success)
    - label_name: Name of the created label (on success)
    - error: Error message (on failure)
    """
    import json
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        category_id = data.get('category_id')
        name = data.get('name', '').strip()
        
        if not category_id:
            return JsonResponse({'success': False, 'error': 'Category ID required'})
        
        if not name:
            return JsonResponse({'success': False, 'error': 'Label name required'})
        
        # Get the category
        from ..models import LabelCategory
        try:
            category = LabelCategory.objects.get(pk=category_id)
        except LabelCategory.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Category not found'})
        
        # Check if label with same name already exists in this category
        if Label.objects.filter(category=category, name__iexact=name).exists():
            return JsonResponse({'success': False, 'error': 'Label already exists in this category'})
        
        # Create the label
        label = Label.objects.create(category=category, name=name)
        
        return JsonResponse({
            'success': True,
            'label_id': label.id,
            'label_name': label.name,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
