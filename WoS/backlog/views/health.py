"""
Health check and utility views for WoS backlog application.

Provides infrastructure endpoints:
- health: Health check for container orchestration
"""
from django.http import JsonResponse

from ..models import Story


def health(request):
    """Health check endpoint for container orchestration.

    Returns 200 OK with JSON if database is accessible, 500 otherwise.
    Useful for Kubernetes/Docker health probes.
    """
    try:
        _ = Story.objects.exists()
        return JsonResponse({'status': 'ok'}, status=200)
    except Exception as e:
        return JsonResponse({'status': 'error', 'detail': str(e)}, status=500)
