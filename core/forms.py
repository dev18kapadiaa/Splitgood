from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from .models import Group, Expense, ExpenseShare, Payment, Comment
from .currencies import CURRENCY_CHOICES
from decimal import Decimal

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
