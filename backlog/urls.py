"""
URL configuration for the backlog application.

URL Structure:
    /backlog/               - Redirect to dashboard
    /backlog/dashboard/     - Dashboard for stories needing attention
    /backlog/stories/       - Story list
    /backlog/story/new/     - Create new story
    /backlog/story/<id>/    - Story detail/edit page (refine)
    /backlog/report/        - WSJF priority report
    /backlog/kanban/        - Kanban board
    /backlog/wbs/           - Work Breakdown Structure
    /backlog/health/        - Health check endpoint
    /backlog/changelog/     - Version changelog
"""
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'backlog'

urlpatterns = [
    # Root redirects to dashboard
    path('', RedirectView.as_view(pattern_name='backlog:dashboard', permanent=False), name='index'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Story URLs
    path('stories/', views.story_list, name='stories'),
    path('stories/bulk/', views.bulk_action, name='stories_bulk_action'),
    path('story/new/', views.create_story_refine, name='story_create'),
    path('story/<int:pk>/', views.refine_story, name='story_detail'),
    
    # Report and visualization
    path('report/', views.report_view, name='report'),
    path('kanban/', views.kanban_view, name='kanban'),
    path('kanban/move/', views.kanban_move, name='kanban_move'),
    path('wbs/', views.wbs_view, name='wbs'),
    path('wbs/add-dependency/', views.wbs_add_dependency, name='wbs_add_dependency'),
    path('wbs/remove-dependency/', views.wbs_remove_dependency, name='wbs_remove_dependency'),
    
    # Labels API
    path('labels/create/', views.create_label, name='create_label'),
    
    # Utility
    path('health/', views.health, name='health'),
    path('changelog/', views.changelog, name='changelog'),
]