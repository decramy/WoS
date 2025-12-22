from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q
from django.http import HttpResponse

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
)


def index(request):
    return HttpResponse("WoS — backlog home")


def epic_list(request):
    # Minimal placeholder view; later replace with templates
    epics = Epic.objects.all()
    titles = ", ".join(e.title for e in epics)
    return HttpResponse(f"Epics: {titles}")


def story_list(request):
    stories = Story.objects.all()
    titles = ", ".join(s.title for s in stories)
    return HttpResponse(f"Stories: {titles}")


def overview(request):
    """Overview: show a list of Epics. Clicking an epic should go to the stories page filtered by that epic."""
    # handle epic create/edit/delete from the overview header inline form
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

    # Filtering & sorting
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'title')
    order = request.GET.get('order', 'asc')

    epics_qs = Epic.objects.prefetch_related('stories').annotate(story_count=Count('stories'))
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
        # first story with target
        target = ''
        workitems = ''
        for s in e.stories.all():
            if not target and s.target and s.target.strip():
                target = s.target.replace('\n', ' ').strip()
            if not workitems and s.workitems and s.workitems.strip():
                workitems = s.workitems.replace('\n', ' ').strip()
            if target and workitems:
                break
        if target and len(target) > 100:
            target = target[:100] + '…'
        if workitems and len(workitems) > 100:
            workitems = workitems[:100] + '…'
        epics.append({'epic': e, 'target': target, 'workitems': workitems})

    context = {
        'epics': epics,
        'q': q,
        'sort': sort,
        'order': order,
    }
    return render(request, 'backlog/overview.html', context)


def refine_story(request, pk):
    """Separate page to refine a story: edit target and workitems."""
    story = get_object_or_404(Story, pk=pk)
    epics = Epic.objects.order_by("title")
    if request.method == "POST":
        # allow updating title and epic here (refinement)
        title = request.POST.get("title")
        if title is not None:
            story.title = title.strip()

        epic_pk = request.POST.get("epic_id")
        if epic_pk:
            story.epic = get_object_or_404(Epic, pk=epic_pk)

        story.target = request.POST.get("target", story.target)
        story.workitems = request.POST.get("workitems", story.workitems)
        story.save()
        return redirect("/backlog/overview/")

    return render(request, "backlog/refine.html", {"story": story, "epics": epics})


def create_story_refine(request):
    """Show the refine template to create a new story.

    On GET: render the same `refine.html` but with an unsaved Story-like object.
    On POST: create the story and redirect to overview.
    """
    epics = Epic.objects.order_by("title")
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        epic_pk = request.POST.get("epic_id")
        target = request.POST.get("target", "").strip()
        workitems = request.POST.get("workitems", "").strip()
        if title and epic_pk:
            epic = get_object_or_404(Epic, pk=epic_pk)
            Story.objects.create(epic=epic, title=title, target=target, workitems=workitems)
            return redirect("/backlog/overview/")
        # if validation fails, fall through to re-render the form with epics

    # create a lightweight story-like object for the template
    class _S:
        def __init__(self):
            self.id = None
            self.title = ""
            self.target = ""
            self.workitems = ""
            self.epic = None

    story = _S()
    return render(request, "backlog/refine.html", {"story": story, "epics": epics})


def story_list(request):
    """List stories (optionally filtered by epic via ?epic=ID). Supports search and sorting."""
    epic_id = request.GET.get('epic')
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'epic')
    order = request.GET.get('order', 'asc')

    qs = Story.objects.select_related('epic')
    if epic_id:
        qs = qs.filter(epic_id=epic_id)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(target__icontains=q) | Q(workitems__icontains=q))

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
    context = {
        'stories': stories,
        'q': q,
        'sort': sort,
        'order': order,
        'epic_id': epic_id,
        'epics': Epic.objects.order_by('title'),
    }
    return render(request, 'backlog/stories.html', context)


def report_view(request):
    # Build report: per-section averages for value and cost factors, per-story totals and ratio
    value_sections = list(
        ValueFactorSection.objects.prefetch_related("valuefactors").order_by("name")
    )
    cost_sections = list(
        CostFactorSection.objects.prefetch_related("costfactors").order_by("name")
    )

    stories_qs = (
        Story.objects.select_related("epic").prefetch_related("scores__answer", "cost_scores__answer").order_by(
            "epic__title",
            "title",
        )
    )

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
        # total columns for the table: Epic, Story, per-value-sections, Total Value,
        # per-cost-sections, Total Cost, Result
        "total_cols": 5 + len(value_sections) + len(cost_sections),
    }
    return render(request, "backlog/report.html", context)


def kanban_view(request):
    # placeholder for kanban board
    return render(request, 'backlog/kanban.html', {})


def create_epic(request):
    """Server-side page to create a new Epic. GET shows a small form, POST creates and redirects to overview."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            Epic.objects.create(title=title, description=description)
            return redirect('backlog:overview')
        # if invalid, fall through and re-render the form with an error
    return render(request, 'backlog/create_epic.html', {})