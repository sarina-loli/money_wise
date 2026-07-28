from django import forms

from .models import HouseholdInvite


class HouseholdInviteForm(forms.Form):
    """Equivalent of the requested `FamilyInvitationForm` — validates the
    invited email against the *specific* household/inviter it's being
    submitted for, which a bare `forms.EmailField()` can't do on its own,
    so `household`/`invited_by` are passed in from the view."""

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'them@example.com',
        }),
    )

    def __init__(self, *args, household=None, invited_by=None, **kwargs):
        self.household = household
        self.invited_by = invited_by
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if self.invited_by and self.invited_by.email and email == self.invited_by.email.lower():
            raise forms.ValidationError("You can't invite yourself.")

        if self.household and self.household.memberships.filter(user__email__iexact=email).exists():
            raise forms.ValidationError('That person is already a member of this household.')

        if self.household and self.household.invites.filter(
            email__iexact=email, status=HouseholdInvite.STATUS_PENDING,
        ).exists():
            raise forms.ValidationError(f'An invite is already pending for {email}.')

        return email
