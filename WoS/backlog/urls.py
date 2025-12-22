from django.urls import path
from . import views

app_name = 'backlog'

urlpatterns = [
    path('', views.index, name='index'),
    path('epics/', views.epic_list, name='epics'),
    path('stories/', views.story_list, name='stories'),
    path('overview/', views.overview, name='overview'),
    path('story/new/refine/', views.create_story_refine, name='create_story_refine'),
    path('story/<int:pk>/refine/', views.refine_story, name='refine_story'),
    path('stories/', views.story_list, name='stories'),
    path('report/', views.report_view, name='report'),
    path('kanban/', views.kanban_view, name='kanban'),
    path('epic/new/', views.create_epic, name='create_epic'),
]