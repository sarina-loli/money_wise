from django.urls import path

from . import views

app_name = 'households'

urlpatterns = [
    path('', views.household_home, name='home'),
    path('create/', views.household_create, name='create'),
    path('invite/', views.household_invite, name='invite'),
    path('invite/<str:token>/accept/', views.household_invite_accept, name='accept_invite'),
    path('members/<int:user_id>/remove/', views.household_remove_member, name='remove_member'),
    path('leave/', views.household_leave, name='leave'),
    path('disband/', views.household_disband, name='disband'),
]
