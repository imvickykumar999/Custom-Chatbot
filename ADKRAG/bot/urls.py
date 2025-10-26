from django.urls import path
from . import views

urlpatterns = [
    path('', views.scrape, name='scrape'),
    path('api/search/', views.api_search, name='api_search'),
    path('api/scrape/', views.api_scrape, name='api_scrape'),
    path('api/scrape/status/<str:user_id>/', views.get_scrape_status, name='get_scrape_status'),
]
