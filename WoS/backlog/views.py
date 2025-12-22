from django.http import HttpResponse

from .models import Epic, Story


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
# This file is intentionally left blank.