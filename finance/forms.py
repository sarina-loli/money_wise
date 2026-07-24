from django import forms

from .models import Budget, Expense, Income, SavingsGoal


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            existing = field.widget.attrs.get('class', '')
            base = 'form-input'
            if isinstance(field.widget, forms.CheckboxInput):
                base = 'checkbox-input'
            field.widget.attrs['class'] = f'{existing} {base}'.strip()


class IncomeForm(StyledModelForm):
    class Meta:
        model = Income
        fields = ['amount', 'category', 'description', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.TextInput(attrs={'placeholder': 'e.g. March salary'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
        }


class ExpenseForm(StyledModelForm):
    class Meta:
        model = Expense
        fields = ['amount', 'category', 'description', 'date', 'receipt']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.TextInput(attrs={'placeholder': 'e.g. Weekly groceries'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
        }


class BudgetForm(StyledModelForm):
    class Meta:
        model = Budget
        fields = ['category', 'monthly_limit', 'month']
        widgets = {
            'month': forms.DateInput(attrs={'type': 'date'}),
            'monthly_limit': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
        }


class SavingsGoalForm(StyledModelForm):
    class Meta:
        model = SavingsGoal
        fields = ['name', 'icon', 'target_amount', 'saved_amount', 'deadline']
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'target_amount': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'saved_amount': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Emergency Fund'}),
            'icon': forms.TextInput(attrs={'placeholder': '🎯'}),
        }


class AddFundsForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0.01,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'placeholder': 'Amount to add'})
    )
