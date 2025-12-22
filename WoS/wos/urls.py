from django.urls import path, include

urlpatterns = [
    path('backlog/', include('backlog.urls')),
]