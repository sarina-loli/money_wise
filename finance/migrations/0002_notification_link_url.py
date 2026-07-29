from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('budget_warning', 'Budget Warning'),
                    ('budget_exceeded', 'Budget Exceeded'),
                    ('goal_completed', 'Goal Completed'),
                    ('reminder', 'Reminder'),
                    ('large_spending', 'Large Spending Alert'),
                    ('monthly_summary', 'Monthly Summary'),
                    ('household_invite', 'Household Invitation'),
                ],
                default='reminder',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='link_url',
            field=models.CharField(blank=True, max_length=300, null=True),
        ),
    ]
