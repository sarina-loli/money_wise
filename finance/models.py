from datetime import date

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse


INCOME_CATEGORIES = [
    ('salary', 'Salary'),
    ('business', 'Business'),
    ('freelance', 'Freelance'),
    ('bonus', 'Bonus'),
    ('gift', 'Gift'),
    ('investment', 'Investment'),
    ('rental', 'Rental'),
    ('other', 'Other'),
]

EXPENSE_CATEGORIES = [
    ('food', 'Food'),
    ('shopping', 'Shopping'),
    ('transport', 'Transport'),
    ('education', 'Education'),
    ('health', 'Health'),
    ('entertainment', 'Entertainment'),
    ('utilities', 'Utilities'),
    ('insurance', 'Insurance'),
    ('travel', 'Travel'),
    ('investment', 'Investment'),
    ('other', 'Other'),
]

NOTIFICATION_TYPES = [
    ('budget_warning', 'Budget Warning'),
    ('budget_exceeded', 'Budget Exceeded'),
    ('goal_completed', 'Goal Completed'),
    ('reminder', 'Reminder'),
    ('large_spending', 'Large Spending Alert'),
    ('monthly_summary', 'Monthly Summary'),
]


class Income(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incomes')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=20, choices=INCOME_CATEGORIES, default='other')
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_category_display()} · {self.amount}'

    def get_absolute_url(self):
        return reverse('finance:income_list')


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES, default='other')
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField(default=date.today)
    receipt = models.ImageField(upload_to='receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_category_display()} · {self.amount}'

    def get_absolute_url(self):
        return reverse('finance:expense_list')


class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES)
    monthly_limit = models.DecimalField(max_digits=12, decimal_places=2)
    month = models.DateField(help_text='Any date within the budgeted month; day is ignored.')
    # When set (Family plan only), every household member sees this budget
    # and its "spent" total is pooled across all of their expenses, not just
    # the creator's.
    household = models.ForeignKey(
        'households.Household', on_delete=models.SET_NULL, null=True, blank=True, related_name='shared_budgets',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month', 'category']
        unique_together = ('user', 'category', 'month')

    def __str__(self):
        return f'{self.get_category_display()} budget · {self.month:%B %Y}'

    def get_absolute_url(self):
        return reverse('finance:budget_list')

    def _expense_filter_users(self):
        if self.household_id:
            return [m.user_id for m in self.household.memberships.all()]
        return [self.user_id]

    def spent(self):
        return Expense.objects.filter(
            user_id__in=self._expense_filter_users(),
            category=self.category,
            date__year=self.month.year,
            date__month=self.month.month,
        ).aggregate(total=models.Sum('amount'))['total'] or 0

    def percent_used(self):
        if not self.monthly_limit:
            return 0
        pct = (float(self.spent()) / float(self.monthly_limit)) * 100
        return round(min(pct, 999), 1)

    def remaining(self):
        return float(self.monthly_limit) - float(self.spent())

    def status(self):
        pct = self.percent_used()
        if pct >= 100:
            return 'exceeded'
        if pct >= 80:
            return 'warning'
        return 'ok'


class SavingsGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='savings_goals')
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    saved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deadline = models.DateField(blank=True, null=True)
    icon = models.CharField(max_length=8, default='🎯')
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('finance:savings_list')

    def percent_complete(self):
        if not self.target_amount:
            return 0
        pct = (float(self.saved_amount) / float(self.target_amount)) * 100
        return round(min(pct, 100), 1)

    def remaining(self):
        return max(float(self.target_amount) - float(self.saved_amount), 0)


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='reminder')
    title = models.CharField(max_length=150)
    message = models.CharField(max_length=300)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def icon(self):
        return {
            'budget_warning': '⚠️',
            'budget_exceeded': '🚨',
            'goal_completed': '🎉',
            'reminder': '⏰',
            'large_spending': '💸',
            'monthly_summary': '📊',
        }.get(self.type, '🔔')
