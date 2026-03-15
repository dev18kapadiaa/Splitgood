from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from .models import Group, Expense, ExpenseShare, Payment, Comment
from .currencies import CURRENCY_CHOICES
from decimal import Decimal
from decimal import InvalidOperation
import json

User = get_user_model()


COUNTRY_CODE_CHOICES = [
    ('+1', '+1 (US/CA)'),
    ('+44', '+44 (UK)'),
    ('+91', '+91 (India)'),
    ('+61', '+61 (Australia)'),
    ('+33', '+33 (France)'),
    ('+49', '+49 (Germany)'),
    ('+81', '+81 (Japan)'),
    ('+86', '+86 (China)'),
    ('+55', '+55 (Brazil)'),
    ('+52', '+52 (Mexico)'),
    ('+82', '+82 (S. Korea)'),
    ('+39', '+39 (Italy)'),
    ('+34', '+34 (Spain)'),
    ('+7', '+7 (Russia)'),
    ('+62', '+62 (Indonesia)'),
    ('+63', '+63 (Philippines)'),
    ('+65', '+65 (Singapore)'),
    ('+971', '+971 (UAE)'),
    ('+972', '+972 (Israel)'),
    ('+234', '+234 (Nigeria)'),
    ('+27', '+27 (S. Africa)'),
    ('+64', '+64 (N. Zealand)'),
]


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email',
            'autocomplete': 'email'
        })
    )
    display_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Your display name'
        })
    )
    country_code = forms.ChoiceField(
        choices=COUNTRY_CODE_CHOICES,
        initial='+1',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-testid': 'select-signup-country-code',
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '2345678901',
            'inputmode': 'tel',
        })
    )

    class Meta:
        model = User
        fields = ('email', 'display_name', 'country_code', 'phone', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Create a password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Confirm your password'
        })

    def clean(self):
        cleaned = super().clean()
        country_code = cleaned.get('country_code', '+1')
        phone = cleaned.get('phone', '').strip()
        if phone and not phone.startswith('+'):
            cleaned['phone'] = f'{country_code}{phone}'
        return cleaned

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        existing = User.objects.filter(email__iexact=email, is_active=True).first()
        if existing:
            if existing.is_oauth_only:
                raise forms.ValidationError('This email is linked to a Google account. Please sign in with Google.')
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        return phone


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password'
        })
    )


class PhoneLoginForm(forms.Form):
    country_code = forms.ChoiceField(
        choices=COUNTRY_CODE_CHOICES,
        initial='+1',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-testid': 'select-country-code',
        })
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '2345678901',
            'autocomplete': 'tel',
            'inputmode': 'tel',
        })
    )

    def clean(self):
        cleaned = super().clean()
        country_code = cleaned.get('country_code', '+1')
        phone = cleaned.get('phone', '').strip()
        if phone.startswith('+'):
            cleaned['phone'] = phone
        else:
            cleaned['phone'] = f'{country_code}{phone}'
        return cleaned


class PhoneOTPVerifyForm(forms.Form):
    otp_code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter 6-digit code',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
        })
    )


class PhoneSetNameForm(forms.Form):
    display_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Your name',
        })
    )


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['display_name', 'currency', 'timezone']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-input'}),
            'currency': forms.Select(attrs={'class': 'form-select'}, choices=CURRENCY_CHOICES),
            'timezone': forms.Select(attrs={'class': 'form-select'}, choices=[
                ('UTC', 'UTC'),
                ('America/New_York', 'Eastern Time'),
                ('America/Chicago', 'Central Time'),
                ('America/Denver', 'Mountain Time'),
                ('America/Los_Angeles', 'Pacific Time'),
                ('Europe/London', 'London'),
                ('Europe/Paris', 'Paris'),
                ('Asia/Tokyo', 'Tokyo'),
                ('Asia/Kolkata', 'India'),
            ]),
        }


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'description', 'default_currency', 'default_split_type', 'group_color']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Group name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Description (optional)',
                'rows': 3
            }),
            'default_currency': forms.Select(attrs={'class': 'form-select'}, choices=CURRENCY_CHOICES),
            'default_split_type': forms.Select(attrs={'class': 'form-select'}),
            'group_color': forms.TextInput(attrs={
                'class': 'form-input',
                'type': 'color'
            }),
        }


class DisplayNameModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.get_display_name()


class DisplayNameModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.get_display_name()


class ExpenseForm(forms.ModelForm):
    participants = DisplayNameModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'participant-checkbox'}),
        required=True
    )
    contributions_json = forms.CharField(required=False, widget=forms.HiddenInput())
    split_values_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Expense
        fields = ['title', 'total_amount', 'currency', 'paid_by', 'date', 'split_type', 'notes', 'receipt_image']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'What was this expense for?'
            }),
            'total_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'currency': forms.Select(attrs={'class': 'form-select'}, choices=CURRENCY_CHOICES),
            'paid_by': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'split_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Add notes (optional)',
                'rows': 2
            }),
            'receipt_image': forms.FileInput(attrs={'class': 'form-input'}),
        }

    def __init__(self, group=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        if group:
            members = group.get_members()
            self.fields['paid_by'] = DisplayNameModelChoiceField(
                queryset=members,
                widget=forms.Select(attrs={'class': 'form-select'}),
            )
            self.fields['participants'].queryset = members
            self.fields['participants'].initial = members
            if not self.instance.pk:
                self.initial['currency'] = group.default_currency

    def _parse_entries(self, raw_text):
        if not raw_text:
            return []
        if isinstance(raw_text, list):
            return raw_text
        try:
            value = json.loads(raw_text)
        except (TypeError, ValueError):
            raise forms.ValidationError('Invalid structured payload for split details.')
        if not isinstance(value, list):
            raise forms.ValidationError('Structured split payload must be a list.')
        return value

    def clean(self):
        cleaned = super().clean()
        total_amount = cleaned.get('total_amount')
        split_type = cleaned.get('split_type')
        participants = cleaned.get('participants')
        paid_by = cleaned.get('paid_by')

        if not total_amount or not participants:
            return cleaned

        participant_ids = {str(u.id) for u in participants}
        group_members = set()
        if self.group:
            group_members = {str(u.id) for u in self.group.get_members()}

        raw_contributions = cleaned.get('contributions_json') or self.data.get('contributions_json', '')
        contribution_entries = self._parse_entries(raw_contributions)
        contributions = []

        if not contribution_entries:
            # Backward compatible fallback: single payer covers full amount.
            contributions = [{'user': paid_by, 'amount': total_amount.quantize(Decimal('0.01'))}]
        else:
            seen_users = set()
            total_contributed = Decimal('0')
            for item in contribution_entries:
                if not isinstance(item, dict):
                    raise forms.ValidationError('Each contribution entry must be an object.')
                user_id = str(item.get('user', '')).strip()
                amount_raw = item.get('amount', '0')
                try:
                    amount = Decimal(str(amount_raw)).quantize(Decimal('0.01'))
                except (InvalidOperation, ValueError):
                    raise forms.ValidationError('Contribution amounts must be valid decimals.')
                if amount <= 0:
                    raise forms.ValidationError('Contribution amounts must be greater than zero.')
                if user_id in seen_users:
                    raise forms.ValidationError('Contributors must be unique.')
                seen_users.add(user_id)
                if self.group and user_id not in group_members:
                    raise forms.ValidationError('All contributors must be group members.')
                user = User.objects.filter(id=user_id).first()
                if not user:
                    raise forms.ValidationError('Contribution user not found.')
                contributions.append({'user': user, 'amount': amount})
                total_contributed += amount

            if total_contributed != total_amount:
                raise forms.ValidationError('Sum of contributions must equal total expense amount.')

        split_entries_raw = cleaned.get('split_values_json') or self.data.get('split_values_json', '')
        split_entries = self._parse_entries(split_entries_raw)
        split_amounts = {}
        split_percentages = {}

        if split_type == 'equal':
            if len(participants) == 0:
                raise forms.ValidationError('At least one participant is required for equal split.')
        elif split_type == 'unequal':
            if split_entries:
                source_entries = split_entries
            else:
                source_entries = []
                for user in participants:
                    source_entries.append({'user': str(user.id), 'amount': self.data.get(f'split_amount_{user.id}', '0')})

            sum_shares = Decimal('0')
            for item in source_entries:
                user_id = str(item.get('user', '')).strip()
                if user_id not in participant_ids:
                    continue
                try:
                    amount = Decimal(str(item.get('amount', '0'))).quantize(Decimal('0.01'))
                except (InvalidOperation, ValueError):
                    raise forms.ValidationError('Unequal split amounts must be valid decimals.')
                if amount < 0:
                    raise forms.ValidationError('Unequal split amounts cannot be negative.')
                split_amounts[user_id] = amount
                sum_shares += amount

            for participant in participants:
                split_amounts.setdefault(str(participant.id), Decimal('0'))
            if sum_shares != total_amount:
                raise forms.ValidationError('Sum of unequal shares must equal total expense amount.')

        elif split_type == 'percentage':
            if not split_entries:
                raise forms.ValidationError('Percentage split requires percentage values for participants.')

            sum_percentages = Decimal('0')
            for item in split_entries:
                user_id = str(item.get('user', '')).strip()
                if user_id not in participant_ids:
                    continue
                try:
                    percent = Decimal(str(item.get('amount', '0'))).quantize(Decimal('0.01'))
                except (InvalidOperation, ValueError):
                    raise forms.ValidationError('Percentage values must be valid decimals.')
                if percent < 0:
                    raise forms.ValidationError('Percentage values cannot be negative.')
                split_percentages[user_id] = percent
                sum_percentages += percent

            if set(split_percentages.keys()) != participant_ids:
                raise forms.ValidationError('Provide percentage for every selected participant.')
            if sum_percentages != Decimal('100.00'):
                raise forms.ValidationError('Sum of percentages must be exactly 100.')

        cleaned['parsed_contributions'] = contributions
        cleaned['parsed_split_amounts'] = split_amounts
        cleaned['parsed_split_percentages'] = split_percentages
        return cleaned


class UnequalSplitForm(forms.Form):
    def __init__(self, participants=None, total_amount=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if participants:
            for user in participants:
                self.fields[f'amount_{user.id}'] = forms.DecimalField(
                    label=user.get_display_name(),
                    max_digits=12,
                    decimal_places=2,
                    min_value=0,
                    required=False,
                    initial=0,
                    widget=forms.NumberInput(attrs={
                        'class': 'form-input split-amount',
                        'step': '0.01',
                        'data-user-id': str(user.id)
                    })
                )


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['from_user', 'to_user', 'amount', 'currency', 'date', 'notes', 'method']
        widgets = {
            'from_user': forms.Select(attrs={'class': 'form-select'}),
            'to_user': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Add notes (optional)',
                'rows': 2
            }),
            'method': forms.Select(attrs={'class': 'form-select'}, choices=[
                ('', 'Select method'),
                ('cash', 'Cash'),
                ('bank_transfer', 'Bank Transfer'),
                ('venmo', 'Venmo'),
                ('paypal', 'PayPal'),
                ('zelle', 'Zelle'),
                ('other', 'Other'),
            ]),
        }

    def __init__(self, group=None, current_user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if group:
            members = group.get_members()
            self.fields['from_user'] = DisplayNameModelChoiceField(
                queryset=members,
                widget=forms.Select(attrs={'class': 'form-select'}),
            )
            self.fields['to_user'] = DisplayNameModelChoiceField(
                queryset=members,
                widget=forms.Select(attrs={'class': 'form-select'}),
            )
            group_currencies = self._get_group_currencies(group)
            currency_choices = [(c, c) for c in group_currencies] if group_currencies else [('USD', 'USD')]
            self.fields['currency'] = forms.ChoiceField(
                choices=currency_choices,
                widget=forms.Select(attrs={'class': 'form-select'}),
            )
        if current_user:
            self.fields['from_user'].initial = current_user

    def _get_group_currencies(self, group):
        from .models import Expense, Payment as PaymentModel
        expense_currencies = set(
            Expense.objects.filter(group=group)
            .values_list('currency', flat=True).distinct()
        )
        payment_currencies = set(
            PaymentModel.objects.filter(group=group)
            .values_list('currency', flat=True).distinct()
        )
        all_currencies = expense_currencies | payment_currencies
        all_currencies.add(group.default_currency)
        return sorted(all_currencies)


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Add a comment...',
                'rows': 2
            })
        }


class InviteMemberForm(forms.Form):
    display_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Name of the person',
        })
    )
    channel = forms.ChoiceField(
        choices=[('email', 'Email'), ('phone', 'Phone')],
        widget=forms.RadioSelect(attrs={'class': 'channel-radio'}),
        initial='email',
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter email address',
        })
    )
    country_code = forms.ChoiceField(
        choices=COUNTRY_CODE_CHOICES,
        initial='+1',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-testid': 'select-invite-country-code',
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '2345678901',
            'inputmode': 'tel',
        })
    )

    def clean(self):
        cleaned = super().clean()
        channel = cleaned.get('channel')
        email = cleaned.get('email', '').strip()
        phone = cleaned.get('phone', '').strip()
        if channel == 'email' and not email:
            self.add_error('email', 'Email is required when using email channel.')
        elif channel == 'phone' and not phone:
            self.add_error('phone', 'Phone number is required when using phone channel.')
        elif channel == 'phone' and phone:
            country_code = cleaned.get('country_code', '+1')
            if not phone.startswith('+'):
                cleaned['phone'] = f'{country_code}{phone}'
        return cleaned


class ForgotPasswordForm(forms.Form):
    channel = forms.ChoiceField(
        choices=[('email', 'Email'), ('phone', 'Phone')],
        widget=forms.RadioSelect(attrs={'class': 'channel-radio'}),
        initial='email',
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email',
            'data-testid': 'input-reset-email',
        })
    )
    country_code = forms.ChoiceField(
        choices=COUNTRY_CODE_CHOICES,
        initial='+1',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-testid': 'select-reset-country-code',
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '2345678901',
            'inputmode': 'tel',
            'data-testid': 'input-reset-phone',
        })
    )

    def clean(self):
        cleaned = super().clean()
        channel = cleaned.get('channel')
        if channel == 'email':
            email = cleaned.get('email', '').strip()
            if not email:
                self.add_error('email', 'Email is required.')
        elif channel == 'phone':
            phone = cleaned.get('phone', '').strip()
            if not phone:
                self.add_error('phone', 'Phone number is required.')
            else:
                country_code = cleaned.get('country_code', '+1')
                if not phone.startswith('+'):
                    cleaned['phone'] = f'{country_code}{phone}'
        return cleaned


class ResetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'New password',
        })
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm new password',
        })
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('new_password1')
        p2 = cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned
