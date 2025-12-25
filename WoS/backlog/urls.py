from django.urls import path
from . import views

app_name = 'backlog'

urlpatterns = [
    path('', views.overview, name='index'),  # /backlog/ shows epics overview
    path('stories/', views.story_list, name='stories'),
    path('story/new/refine/', views.create_story_refine, name='create_story_refine'),
    path('story/<int:pk>/refine/', views.refine_story, name='refine_story'),
    path('report/', views.report_view, name='report'),
    path('kanban/', views.kanban_view, name='kanban'),
    path('kanban/move/', views.kanban_move, name='kanban_move'),
    path('wbs/', views.wbs_view, name='wbs'),
    path('wbs/add-dependency/', views.wbs_add_dependency, name='wbs_add_dependency'),
    path('wbs/remove-dependency/', views.wbs_remove_dependency, name='wbs_remove_dependency'),
    path('health/', views.health, name='health'),
    path('epic/new/', views.create_epic, name='create_epic'),
    path('epic/<int:pk>/edit/', views.edit_epic, name='edit_epic'),
]