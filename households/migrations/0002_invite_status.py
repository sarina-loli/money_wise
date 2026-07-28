from django.db import migrations, models


def populate_status_from_accepted(apps, schema_editor):
    """Backfill status/accepted_at for any invites that existed before this
    migration, so previously-accepted invites aren't silently reset back
    to 'pending'."""
    HouseholdInvite = apps.get_model('households', 'HouseholdInvite')
    HouseholdInvite.objects.filter(accepted=True).update(status='accepted')
    for invite in HouseholdInvite.objects.filter(status='accepted', accepted_at__isnull=True):
        invite.accepted_at = invite.created_at
        invite.save(update_fields=['accepted_at'])


def reverse_noop(apps, schema_editor):
    # Nothing to reverse — the old 'accepted' column is gone by this point
    # (removed later in this same migration), so there's no data to move
    # back into it.
    pass


def dedupe_pending_invites(apps, schema_editor):
    """Guard for the AddConstraint step below: if any (household, email)
    pair already has more than one 'pending' invite (possible under the
    old code, which had no duplicate check), keep only the most recent
    one and mark the rest 'expired' so the new UniqueConstraint can be
    added without failing on old data."""
    HouseholdInvite = apps.get_model('households', 'HouseholdInvite')
    from django.db.models import Count

    dupes = (
        HouseholdInvite.objects.filter(status='pending')
        .values('household_id', 'email')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
    )
    for row in dupes:
        ids = list(
            HouseholdInvite.objects.filter(
                household_id=row['household_id'], email=row['email'], status='pending',
            ).order_by('-created_at').values_list('id', flat=True)
        )
        HouseholdInvite.objects.filter(id__in=ids[1:]).update(status='expired')


class Migration(migrations.Migration):

    dependencies = [
        ('households', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='householdinvite',
            name='status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('expired', 'Expired')],
                default='pending',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='householdinvite',
            name='accepted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(populate_status_from_accepted, reverse_noop),
        migrations.RemoveField(
            model_name='householdinvite',
            name='accepted',
        ),
        migrations.AlterModelOptions(
            name='householdinvite',
            options={'ordering': ['-created_at']},
        ),
        migrations.RunPython(dedupe_pending_invites, reverse_noop),
        migrations.AddConstraint(
            model_name='householdinvite',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'pending')),
                fields=('household', 'email'),
                name='unique_pending_invite_per_email',
            ),
        ),
    ]
