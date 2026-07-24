import calendar as cal_module
import csv
import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.core.paginator import Paginator

from .forms import AddFundsForm, BudgetForm, ExpenseForm, IncomeForm, SavingsGoalForm
from .models import (
    EXPENSE_CATEGORIES,
    Budget,
    Expense,
    INCOME_CATEGORIES,
    Income,
    Notification,
    SavingsGoal,
)
from billing.plans import EXPORT_ALLOWED_PLANS, SAVINGS_GOAL_LIMITS
from households.models import get_household


def _month_bounds(d):
    start = d.replace(day=1)
    last_day = cal_module.monthrange(d.year, d.month)[1]
    end = d.replace(day=last_day)
    return start, end


def _check_budget_alerts(user, expense):
    """Create a notification if adding this expense pushes a budget into
    warning (80%+) or exceeded (100%+) territory."""
    start, _ = _month_bounds(expense.date)
    budget = Budget.objects.filter(user=user, category=expense.category,
                                    month__year=expense.date.year,
                                    month__month=expense.date.month).first()
    if not budget:
        return
    pct = budget.percent_used()
    if pct >= 100:
        Notification.objects.get_or_create(
            user=user, type='budget_exceeded',
            title=f'{budget.get_category_display()} budget exceeded',
            message=f'You have spent {pct}% of your {budget.get_category_display()} budget for {budget.month:%B}.',
            defaults={'is_read': False},
        )
    elif pct >= 80:
        Notification.objects.get_or_create(
            user=user, type='budget_warning',
            title=f'{budget.get_category_display()} budget warning',
            message=f'You have used {pct}% of your {budget.get_category_display()} budget for {budget.month:%B}.',
            defaults={'is_read': False},
        )
    if expense.amount >= 500:
        Notification.objects.create(
            user=user, type='large_spending',
            title='Large expense recorded',
            message=f'A {expense.get_category_display()} expense of {expense.amount} was recorded.',
        )


# --------------------------------------------------------------------------
# DASHBOARD
# --------------------------------------------------------------------------
@login_required
def dashboard(request):
    user = request.user
    today = date.today()
    start, end = _month_bounds(today)

    month_income = Income.objects.filter(user=user, date__range=(start, end)).aggregate(t=Sum('amount'))['t'] or 0
    month_expense = Expense.objects.filter(user=user, date__range=(start, end)).aggregate(t=Sum('amount'))['t'] or 0
    total_balance = (Income.objects.filter(user=user).aggregate(t=Sum('amount'))['t'] or 0) - \
                     (Expense.objects.filter(user=user).aggregate(t=Sum('amount'))['t'] or 0)

    budgets = Budget.objects.filter(user=user, month__year=today.year, month__month=today.month)
    total_budgeted = sum(float(b.monthly_limit) for b in budgets) or 0
    remaining_budget = total_budgeted - float(month_expense)

    savings_goals = SavingsGoal.objects.filter(user=user).order_by('is_completed', '-created_at')[:4]

    recent_income = [{'kind': 'income', 'obj': i} for i in Income.objects.filter(user=user)[:5]]
    recent_expense = [{'kind': 'expense', 'obj': e} for e in Expense.objects.filter(user=user)[:5]]
    recent_transactions = sorted(
        recent_income + recent_expense,
        key=lambda t: (t['obj'].date, t['obj'].created_at), reverse=True
    )[:6]

    # Category breakdown (this month's expenses) for pie chart
    category_data = (
        Expense.objects.filter(user=user, date__range=(start, end))
        .values('category').annotate(total=Sum('amount')).order_by('-total')
    )
    category_labels = [dict(EXPENSE_CATEGORIES).get(c['category'], c['category']) for c in category_data]
    category_values = [float(c['total']) for c in category_data]

    # Income vs Expense over the last 6 months for line/bar chart
    months, income_series, expense_series = [], [], []
    cursor = today.replace(day=1)
    for i in range(5, -1, -1):
        year = cursor.year
        month = cursor.month - i
        while month <= 0:
            month += 12
            year -= 1
        m_start = date(year, month, 1)
        m_end_day = cal_module.monthrange(year, month)[1]
        m_end = date(year, month, m_end_day)
        months.append(m_start.strftime('%b'))
        income_series.append(float(Income.objects.filter(user=user, date__range=(m_start, m_end)).aggregate(t=Sum('amount'))['t'] or 0))
        expense_series.append(float(Expense.objects.filter(user=user, date__range=(m_start, m_end)).aggregate(t=Sum('amount'))['t'] or 0))

    unread_notifications = Notification.objects.filter(user=user, is_read=False).count()

    # Simple financial health score: 100 minus overspend penalty, plus savings bonus
    score = 70
    if total_budgeted:
        used_pct = (float(month_expense) / total_budgeted) * 100
        score = max(0, min(100, int(100 - max(0, used_pct - 60))))

    context = {
        'month_income': month_income,
        'month_expense': month_expense,
        'total_balance': total_balance,
        'remaining_budget': remaining_budget,
        'total_budgeted': total_budgeted,
        'budgets': budgets[:4],
        'savings_goals': savings_goals,
        'recent_transactions': recent_transactions,
        'category_labels': json.dumps(category_labels),
        'category_values': json.dumps(category_values),
        'trend_months': json.dumps(months),
        'trend_income': json.dumps(income_series),
        'trend_expense': json.dumps(expense_series),
        'unread_notifications': unread_notifications,
        'health_score': score,
        'today': today,
    }
    return render(request, 'finance/dashboard.html', context)


# --------------------------------------------------------------------------
# INCOME CRUD
# --------------------------------------------------------------------------
@login_required
def income_list(request):
    qs = Income.objects.filter(user=request.user)
    query = request.GET.get('q', '')
    if query:
        qs = qs.filter(description__icontains=query)
    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category=category)

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    total = qs.aggregate(t=Sum('amount'))['t'] or 0

    return render(request, 'finance/income_list.html', {
        'page_obj': page_obj, 'query': query, 'category': category,
        'categories': INCOME_CATEGORIES, 'total': total,
    })


@login_required
def income_create(request):
    if request.method == 'POST':
        form = IncomeForm(request.POST)
        if form.is_valid():
            income = form.save(commit=False)
            income.user = request.user
            income.save()
            messages.success(request, 'Income added successfully.')
            return redirect('finance:income_list')
    else:
        form = IncomeForm()
    return render(request, 'finance/income_form.html', {'form': form, 'is_edit': False})


@login_required
def income_update(request, pk):
    income = get_object_or_404(Income, pk=pk, user=request.user)
    if request.method == 'POST':
        form = IncomeForm(request.POST, instance=income)
        if form.is_valid():
            form.save()
            messages.success(request, 'Income updated.')
            return redirect('finance:income_list')
    else:
        form = IncomeForm(instance=income)
    return render(request, 'finance/income_form.html', {'form': form, 'is_edit': True, 'object': income})


@login_required
def income_delete(request, pk):
    income = get_object_or_404(Income, pk=pk, user=request.user)
    if request.method == 'POST':
        income.delete()
        messages.success(request, 'Income deleted.')
        return redirect('finance:income_list')
    return render(request, 'finance/confirm_delete.html', {'object': income, 'type_label': 'income entry'})


# --------------------------------------------------------------------------
# EXPENSE CRUD
# --------------------------------------------------------------------------
@login_required
def expense_list(request):
    qs = Expense.objects.filter(user=request.user)
    query = request.GET.get('q', '')
    if query:
        qs = qs.filter(description__icontains=query)
    category = request.GET.get('category', '')
    if category:
        qs = qs.filter(category=category)

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    total = qs.aggregate(t=Sum('amount'))['t'] or 0

    return render(request, 'finance/expense_list.html', {
        'page_obj': page_obj, 'query': query, 'category': category,
        'categories': EXPENSE_CATEGORIES, 'total': total,
    })


@login_required
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            _check_budget_alerts(request.user, expense)
            messages.success(request, 'Expense added successfully.')
            return redirect('finance:expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'finance/expense_form.html', {'form': form, 'is_edit': False})


@login_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated.')
            return redirect('finance:expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'finance/expense_form.html', {'form': form, 'is_edit': True, 'object': expense})


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
        return redirect('finance:expense_list')
    return render(request, 'finance/confirm_delete.html', {'object': expense, 'type_label': 'expense entry'})


# --------------------------------------------------------------------------
# TRANSACTIONS (combined read-only view)
# --------------------------------------------------------------------------
@login_required
def transactions(request):
    user = request.user
    txn_type = request.GET.get('type', 'all')
    query = request.GET.get('q', '')

    income_qs = Income.objects.filter(user=user)
    expense_qs = Expense.objects.filter(user=user)
    if query:
        income_qs = income_qs.filter(description__icontains=query)
        expense_qs = expense_qs.filter(description__icontains=query)

    items = []
    if txn_type in ('all', 'income'):
        items += [{'kind': 'income', 'obj': i} for i in income_qs]
    if txn_type in ('all', 'expense'):
        items += [{'kind': 'expense', 'obj': e} for e in expense_qs]
    items.sort(key=lambda x: (x['obj'].date, x['obj'].created_at), reverse=True)

    paginator = Paginator(items, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'finance/transactions.html', {
        'page_obj': page_obj, 'txn_type': txn_type, 'query': query,
    })


# --------------------------------------------------------------------------
# BUDGETS
# --------------------------------------------------------------------------
@login_required
def budget_list(request):
    today = date.today()
    budgets = list(Budget.objects.filter(user=request.user, month__year=today.year, month__month=today.month))
    household = get_household(request.user)
    if household:
        shared = Budget.objects.filter(
            household=household, month__year=today.year, month__month=today.month,
        ).exclude(user=request.user)
        budgets += list(shared)
    return render(request, 'finance/budget_list.html', {'budgets': budgets, 'today': today, 'household': household})


@login_required
def budget_create(request):
    household = get_household(request.user)
    can_share = bool(household and request.user.profile.is_family)
    if request.method == 'POST':
        form = BudgetForm(request.POST)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            if can_share and request.POST.get('share_with_household'):
                budget.household = household
            try:
                budget.save()
                messages.success(request, 'Budget created.')
                return redirect('finance:budget_list')
            except Exception:
                messages.error(request, 'A budget for that category and month already exists.')
    else:
        form = BudgetForm(initial={'month': date.today()})
    return render(request, 'finance/budget_form.html', {'form': form, 'is_edit': False, 'can_share': can_share})


@login_required
def budget_update(request, pk):
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget)
        if form.is_valid():
            form.save()
            messages.success(request, 'Budget updated.')
            return redirect('finance:budget_list')
    else:
        form = BudgetForm(instance=budget)
    return render(request, 'finance/budget_form.html', {'form': form, 'is_edit': True, 'object': budget})


@login_required
def budget_delete(request, pk):
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method == 'POST':
        budget.delete()
        messages.success(request, 'Budget deleted.')
        return redirect('finance:budget_list')
    return render(request, 'finance/confirm_delete.html', {'object': budget, 'type_label': 'budget'})


# --------------------------------------------------------------------------
# SAVINGS GOALS
# --------------------------------------------------------------------------
@login_required
def savings_list(request):
    goals = SavingsGoal.objects.filter(user=request.user)
    add_funds_form = AddFundsForm()
    return render(request, 'finance/savings_list.html', {'goals': goals, 'add_funds_form': add_funds_form})


@login_required
def savings_create(request):
    profile = request.user.profile
    limit = SAVINGS_GOAL_LIMITS.get(profile.plan, 1)
    if limit is not None and SavingsGoal.objects.filter(user=request.user).count() >= limit:
        messages.warning(
            request,
            f'The Free plan includes {limit} savings goal. Upgrade to Pro for unlimited goals.',
        )
        return redirect('finance:savings_list')

    if request.method == 'POST':
        form = SavingsGoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.is_completed = goal.saved_amount >= goal.target_amount
            goal.save()
            messages.success(request, 'Savings goal created.')
            return redirect('finance:savings_list')
    else:
        form = SavingsGoalForm()
    return render(request, 'finance/savings_form.html', {'form': form, 'is_edit': False})


@login_required
def savings_update(request, pk):
    goal = get_object_or_404(SavingsGoal, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SavingsGoalForm(request.POST, instance=goal)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.is_completed = goal.saved_amount >= goal.target_amount
            goal.save()
            messages.success(request, 'Savings goal updated.')
            return redirect('finance:savings_list')
    else:
        form = SavingsGoalForm(instance=goal)
    return render(request, 'finance/savings_form.html', {'form': form, 'is_edit': True, 'object': goal})


@login_required
def savings_delete(request, pk):
    goal = get_object_or_404(SavingsGoal, pk=pk, user=request.user)
    if request.method == 'POST':
        goal.delete()
        messages.success(request, 'Savings goal deleted.')
        return redirect('finance:savings_list')
    return render(request, 'finance/confirm_delete.html', {'object': goal, 'type_label': 'savings goal'})


@login_required
def savings_add_funds(request, pk):
    goal = get_object_or_404(SavingsGoal, pk=pk, user=request.user)
    if request.method == 'POST':
        form = AddFundsForm(request.POST)
        if form.is_valid():
            was_completed = goal.is_completed
            goal.saved_amount = Decimal(goal.saved_amount) + form.cleaned_data['amount']
            if goal.saved_amount >= goal.target_amount:
                goal.is_completed = True
                if not was_completed:
                    Notification.objects.create(
                        user=request.user, type='goal_completed',
                        title='Savings goal reached! 🎉',
                        message=f'You hit your target for "{goal.name}". Amazing work!',
                    )
            goal.save()
            messages.success(request, f'Added funds to "{goal.name}".')
    return redirect('finance:savings_list')


# --------------------------------------------------------------------------
# REPORTS
# --------------------------------------------------------------------------
@login_required
def reports(request):
    user = request.user
    period = request.GET.get('period', 'monthly')
    today = date.today()

    if period == 'yearly':
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
        label_fmt = '%b'
        buckets = 12
    elif period == 'weekly':
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        label_fmt = '%a'
        buckets = 7
    else:  # monthly (daily buckets across current month)
        start, end = _month_bounds(today)
        label_fmt = '%d'
        buckets = (end - start).days + 1

    incomes = Income.objects.filter(user=user, date__range=(start, end))
    expenses = Expense.objects.filter(user=user, date__range=(start, end))

    total_income = incomes.aggregate(t=Sum('amount'))['t'] or 0
    total_expense = expenses.aggregate(t=Sum('amount'))['t'] or 0

    labels, income_series, expense_series = [], [], []
    if period == 'yearly':
        for m in range(1, 13):
            m_start = date(today.year, m, 1)
            m_end = date(today.year, m, cal_module.monthrange(today.year, m)[1])
            labels.append(m_start.strftime(label_fmt))
            income_series.append(float(incomes.filter(date__range=(m_start, m_end)).aggregate(t=Sum('amount'))['t'] or 0))
            expense_series.append(float(expenses.filter(date__range=(m_start, m_end)).aggregate(t=Sum('amount'))['t'] or 0))
    else:
        cursor = start
        while cursor <= end:
            labels.append(cursor.strftime(label_fmt))
            income_series.append(float(incomes.filter(date=cursor).aggregate(t=Sum('amount'))['t'] or 0))
            expense_series.append(float(expenses.filter(date=cursor).aggregate(t=Sum('amount'))['t'] or 0))
            cursor += timedelta(days=1)

    category_data = expenses.values('category').annotate(total=Sum('amount')).order_by('-total')
    category_labels = [dict(EXPENSE_CATEGORIES).get(c['category'], c['category']) for c in category_data]
    category_values = [float(c['total']) for c in category_data]

    context = {
        'period': period, 'start': start, 'end': end,
        'total_income': total_income, 'total_expense': total_expense,
        'net': float(total_income) - float(total_expense),
        'labels': json.dumps(labels),
        'income_series': json.dumps(income_series),
        'expense_series': json.dumps(expense_series),
        'category_labels': json.dumps(category_labels),
        'category_values': json.dumps(category_values),
        'incomes': incomes.order_by('-date')[:50],
        'expenses': expenses.order_by('-date')[:50],
    }
    return render(request, 'finance/reports.html', context)


@login_required
def export_csv(request):
    """'Excel export' — a CSV that opens natively in Excel/Sheets."""
    if request.user.profile.plan not in EXPORT_ALLOWED_PLANS:
        messages.warning(request, 'CSV/Excel export is a Pro feature. Upgrade to unlock it.')
        return redirect('finance:reports')
    user = request.user
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="moneywise_transactions_{date.today()}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Type', 'Date', 'Category', 'Description', 'Amount'])
    for i in Income.objects.filter(user=user):
        writer.writerow(['Income', i.date, i.get_category_display(), i.description, i.amount])
    for e in Expense.objects.filter(user=user):
        writer.writerow(['Expense', e.date, e.get_category_display(), e.description, e.amount])
    return response


@login_required
def export_pdf(request):
    """'PDF export' — a clean print-friendly page; the user saves as PDF
    via the browser's print dialog (avoids extra binary dependencies)."""
    if request.user.profile.plan not in EXPORT_ALLOWED_PLANS:
        messages.warning(request, 'PDF export is a Pro feature. Upgrade to unlock it.')
        return redirect('finance:reports')
    user = request.user
    incomes = Income.objects.filter(user=user).order_by('-date')[:200]
    expenses = Expense.objects.filter(user=user).order_by('-date')[:200]
    total_income = incomes.aggregate(t=Sum('amount'))['t'] or 0
    total_expense = expenses.aggregate(t=Sum('amount'))['t'] or 0
    return render(request, 'finance/export_print.html', {
        'incomes': incomes, 'expenses': expenses,
        'total_income': total_income, 'total_expense': total_expense,
        'generated': date.today(),
    })


# --------------------------------------------------------------------------
# NOTIFICATIONS
# --------------------------------------------------------------------------
@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user)
    return render(request, 'finance/notifications.html', {'notifications': notifs})


@login_required
def notification_mark_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    return redirect('finance:notifications')


@login_required
def notifications_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('finance:notifications')


# --------------------------------------------------------------------------
# CALENDAR
# --------------------------------------------------------------------------
@login_required
def calendar_view(request):
    user = request.user
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    cal_module.setfirstweekday(cal_module.SUNDAY)
    month_days = cal_module.monthcalendar(year, month)

    start = date(year, month, 1)
    end = date(year, month, cal_module.monthrange(year, month)[1])

    day_totals = {}
    for i in Income.objects.filter(user=user, date__range=(start, end)):
        day_totals.setdefault(i.date.day, {'income': 0, 'expense': 0})
        day_totals[i.date.day]['income'] += float(i.amount)
    for e in Expense.objects.filter(user=user, date__range=(start, end)):
        day_totals.setdefault(e.date.day, {'income': 0, 'expense': 0})
        day_totals[e.date.day]['expense'] += float(e.amount)

    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year

    return render(request, 'finance/calendar.html', {
        'weeks': month_days, 'day_totals': day_totals,
        'month_name': start.strftime('%B'), 'year': year, 'month': month,
        'prev_month': prev_month, 'prev_year': prev_year,
        'next_month': next_month, 'next_year': next_year,
        'today': today,
    })
