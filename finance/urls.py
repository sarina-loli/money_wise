from django.urls import path

from . import views

app_name = 'finance'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),

    path('income/', views.income_list, name='income_list'),
    path('income/add/', views.income_create, name='income_create'),
    path('income/<int:pk>/edit/', views.income_update, name='income_update'),
    path('income/<int:pk>/delete/', views.income_delete, name='income_delete'),

    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/add/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_update, name='expense_update'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    path('transactions/', views.transactions, name='transactions'),

    path('budgets/', views.budget_list, name='budget_list'),
    path('budgets/add/', views.budget_create, name='budget_create'),
    path('budgets/<int:pk>/edit/', views.budget_update, name='budget_update'),
    path('budgets/<int:pk>/delete/', views.budget_delete, name='budget_delete'),

    path('savings/', views.savings_list, name='savings_list'),
    path('savings/add/', views.savings_create, name='savings_create'),
    path('savings/<int:pk>/edit/', views.savings_update, name='savings_update'),
    path('savings/<int:pk>/delete/', views.savings_delete, name='savings_delete'),
    path('savings/<int:pk>/add-funds/', views.savings_add_funds, name='savings_add_funds'),

    path('reports/', views.reports, name='reports'),
    path('reports/export/csv/', views.export_csv, name='export_csv'),
    path('reports/export/pdf/', views.export_pdf, name='export_pdf'),

    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),

    path('calendar/', views.calendar_view, name='calendar'),
]
