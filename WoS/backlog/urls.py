from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('epics/', views.epic_list, name='epic_list'),
    path('stories/', views.story_list, name='story_list'),
]