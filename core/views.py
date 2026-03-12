from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, F
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.files.base import ContentFile
from decimal import Decimal
from collections import defaultdict
import uuid
import random
import json
import base64
import binascii
from io import BytesIO
from datetime import timedelta
from PIL import Image, ImageOps
from cloudinary import uploader

from .models import (
    Group, GroupMembership, Expense, ExpenseShare,
    Payment, Comment, Activity, GroupInvite,
    PersonIdentity, PhoneOTP, Profile
)
from .forms import (
    SignUpForm, LoginForm, UserProfileForm, GroupForm,
    ExpenseForm, PaymentForm, CommentForm, InviteMemberForm,
    PhoneLoginForm, PhoneOTPVerifyForm,
    ForgotPasswordForm, ResetPasswordForm
)

User = get_user_model()


def _decode_cropped_profile_image(base64_payload):
    if not base64_payload or ';base64,' not in base64_payload:
        raise ValueError('Invalid image payload.')

    _, encoded = base64_payload.split(';base64,', 1)
    try:
        raw_data = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        raise ValueError('Unable to decode image data.')

    try:
        image = Image.open(BytesIO(raw_data))
    except Exception:
        raise ValueError('Unsupported image file.')

    image = ImageOps.exif_transpose(image).convert('RGB')
    image = ImageOps.fit(
        image,
        (500, 500),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )

    output = BytesIO()
    image.save(output, format='JPEG', quality=95, optimize=True)
    output.seek(0)
    return ContentFile(output.read(), name=f'profile_{uuid.uuid4().hex}.jpg')


def _replace_profile_picture(profile, image_file):
    old_public_id = None
    if profile.image:
        old_public_id = getattr(profile.image, 'public_id', None)
        if not old_public_id:
            old_public_id = str(profile.image)

    upload_result = uploader.upload(
        image_file,
        folder='profile_pictures',
        resource_type='image',
        format='jpg',
    )

    new_public_id = upload_result.get('public_id')
    if not new_public_id:
        raise ValueError('Could not upload profile picture. Please try again.')

    profile.image = new_public_id
    profile.save(update_fields=['image', 'updated_at'])

    saved_public_id = None
    if profile.image:
        saved_public_id = getattr(profile.image, 'public_id', None)
        if not saved_public_id:
            saved_public_id = str(profile.image)

    if old_public_id and old_public_id != saved_public_id:
        try:
            uploader.destroy(old_public_id, invalidate=True, resource_type='image')
        except Exception:
            pass


def _remove_profile_picture(profile):
    old_public_id = None
    if profile.image:
        old_public_id = getattr(profile.image, 'public_id', None)
        if not old_public_id:
            old_public_id = str(profile.image)

    profile.image = None
    profile.save(update_fields=['image', 'updated_at'])

    if old_public_id:
        try:
            uploader.destroy(old_public_id, invalidate=True, resource_type='image')
        except Exception:
            pass


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/home.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            request.session['signup_data'] = {
                'email': form.cleaned_data['email'],
                'display_name': form.cleaned_data['display_name'],
                'phone': form.cleaned_data['phone'],
                'password': form.cleaned_data['password1'],
            }
            phone = form.cleaned_data['phone']
            otp_code = f'{random.randint(0, 999999):06d}'
            PhoneOTP.objects.create(
                phone=phone,
                otp_code=otp_code,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            try:
                from .tasks import send_otp_sms
                send_otp_sms.delay(phone, otp_code)
            except Exception:
                pass
            request.session['signup_otp_phone'] = phone
            messages.info(request, 'Verification code sent to your phone.')
            return redirect('signup_verify')
    else:
        form = SignUpForm()
    return render(request, 'core/signup.html', {'form': form})


def signup_verify(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    signup_data = request.session.get('signup_data')
    phone = request.session.get('signup_otp_phone')
    if not signup_data or not phone:
        return redirect('signup')

    if request.method == 'POST':
        form = PhoneOTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            otp = PhoneOTP.objects.filter(
                phone=phone, is_used=False,
            ).order_by('-created_at').first()

            if not otp:
                messages.error(request, 'Code expired. Please sign up again.')
                return redirect('signup')

            otp.attempts += 1
            otp.save(update_fields=['attempts'])

            if not otp.is_valid():
                messages.error(request, 'Code expired or too many attempts. Please sign up again.')
                return redirect('signup')

            if otp.otp_code != code:
                messages.error(request, 'Invalid code. Please try again.')
                return render(request, 'core/signup_verify.html', {'form': form, 'phone': phone})

            otp.is_used = True
            otp.save(update_fields=['is_used'])

            with transaction.atomic():
                user = User.objects.create_user(
                    username=signup_data['email'],
                    email=signup_data['email'],
                    phone=phone,
                    display_name=signup_data['display_name'],
                    password=signup_data['password'],
                )
                _link_person_identities_for_user(user)

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            for key in ['signup_data', 'signup_otp_phone']:
                request.session.pop(key, None)
            messages.success(request, 'Welcome to Splitgood!')
            return redirect('dashboard')
    else:
        form = PhoneOTPVerifyForm()

    return render(request, 'core/signup_verify.html', {'form': form, 'phone': phone})


def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome back, {user.get_display_name()}!')
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
    else:
        form = LoginForm()

    return render(request, 'core/login.html', {'form': form})


def forgot_password(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            channel = form.cleaned_data['channel']
            user = None

            if channel == 'email':
                email = form.cleaned_data.get('email', '').strip()
                user = User.objects.filter(email__iexact=email, is_active=True).first()
                if not user:
                    messages.error(request, 'No account exists with this email.')
                    return render(request, 'core/forgot_password.html', {'form': form})
            else:
                phone = form.cleaned_data.get('phone', '').strip()
                user = User.objects.filter(phone=phone, is_active=True).first()
                if not user:
                    messages.error(request, 'No account exists with this phone number.')
                    return render(request, 'core/forgot_password.html', {'form': form})

            if user.is_oauth_only:
                return render(request, 'core/forgot_password.html', {'form': form, 'show_google': True})

            phone = user.phone
            if phone:
                otp_code = f'{random.randint(0, 999999):06d}'
                PhoneOTP.objects.create(
                    phone=phone,
                    otp_code=otp_code,
                    expires_at=timezone.now() + timedelta(minutes=10),
                )
                try:
                    from .tasks import send_otp_sms
                    send_otp_sms.delay(phone, otp_code)
                except Exception:
                    pass
                request.session['reset_phone'] = phone
                request.session['reset_user_id'] = str(user.id)
                messages.info(request, f'Verification code sent to your phone ending in ...{phone[-4:]}.')
                return redirect('reset_password_verify')
            else:
                from django.core.mail import send_mail
                otp_code = f'{random.randint(0, 999999):06d}'
                PhoneOTP.objects.create(
                    phone=f'email:{user.email}',
                    otp_code=otp_code,
                    expires_at=timezone.now() + timedelta(minutes=10),
                )
                send_mail(
                    subject='Splitgood Password Reset Code',
                    message=f'Your Splitgood password reset code is: {otp_code}',
                    from_email='noreply@splitgood.app',
                    recipient_list=[user.email],
                    fail_silently=True,
                )
                request.session['reset_phone'] = f'email:{user.email}'
                request.session['reset_user_id'] = str(user.id)
                messages.info(request, 'A reset code has been sent to your email.')
                return redirect('reset_password_verify')
    else:
        form = ForgotPasswordForm()

    return render(request, 'core/forgot_password.html', {'form': form})


def reset_password_verify(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    reset_phone = request.session.get('reset_phone')
    reset_user_id = request.session.get('reset_user_id')
    if not reset_phone or not reset_user_id:
        return redirect('forgot_password')
    
    if request.method == 'POST':
        otp_form = PhoneOTPVerifyForm(request.POST)
        password_form = ResetPasswordForm(request.POST)
        
        if otp_form.is_valid() and password_form.is_valid():
            code = otp_form.cleaned_data['otp_code']
            otp = PhoneOTP.objects.filter(
                phone=reset_phone, is_used=False,
            ).order_by('-created_at').first()
            
            if not otp:
                messages.error(request, 'Code expired. Please request a new one.')
                return redirect('forgot_password')
            
            otp.attempts += 1
            otp.save(update_fields=['attempts'])
            
            if not otp.is_valid():
                messages.error(request, 'Code expired or too many attempts. Please request a new one.')
                return redirect('forgot_password')
            
            if otp.otp_code != code:
                messages.error(request, 'Invalid code. Please try again.')
                return render(request, 'core/reset_password_verify.html', {
                    'otp_form': otp_form, 'password_form': password_form, 'reset_phone': reset_phone
                })
            
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            
            try:
                user = User.objects.get(id=reset_user_id)
                user.set_password(password_form.cleaned_data['new_password1'])
                user.save()
                
                for key in ['reset_phone', 'reset_user_id']:
                    request.session.pop(key, None)
                
                messages.success(request, 'Password reset successfully! Please sign in with your new password.')
                return redirect('login')
            except User.DoesNotExist:
                messages.error(request, 'Account not found.')
                return redirect('forgot_password')
    else:
        otp_form = PhoneOTPVerifyForm()
        password_form = ResetPasswordForm()
    
    return render(request, 'core/reset_password_verify.html', {
        'otp_form': otp_form, 'password_form': password_form, 'reset_phone': reset_phone
    })


def user_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


def phone_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = PhoneLoginForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone'].strip()
            user = User.objects.filter(phone=phone, is_active=True).first()
            if not user:
                messages.error(request, 'This phone number is not registered. Please sign up first.')
                return render(request, 'core/phone_login.html', {'form': form})

            otp_code = f'{random.randint(0, 999999):06d}'
            PhoneOTP.objects.create(
                phone=phone,
                otp_code=otp_code,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            try:
                from .tasks import send_otp_sms
                send_otp_sms.delay(phone, otp_code)
            except Exception:
                pass

            request.session['otp_phone'] = phone
            messages.info(request, 'Verification code sent! Check your phone.')
            return redirect('phone_verify')
    else:
        form = PhoneLoginForm()

    return render(request, 'core/phone_login.html', {'form': form})


def phone_verify(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    phone = request.session.get('otp_phone')
    if not phone:
        return redirect('phone_login')

    if request.method == 'POST':
        form = PhoneOTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            otp = PhoneOTP.objects.filter(
                phone=phone,
                is_used=False,
            ).order_by('-created_at').first()

            if not otp:
                messages.error(request, 'Code expired. Please request a new one.')
                return redirect('phone_login')

            otp.attempts += 1
            otp.save(update_fields=['attempts'])

            if not otp.is_valid():
                messages.error(request, 'Code expired or too many attempts. Please try again.')
                return redirect('phone_login')

            if otp.otp_code != code:
                messages.error(request, 'Invalid code. Please try again.')
                return render(request, 'core/phone_verify.html', {'form': form, 'phone': phone})

            otp.is_used = True
            otp.save(update_fields=['is_used'])

            user = User.objects.filter(phone=phone, is_active=True).first()
            if user:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome back, {user.get_display_name()}!')
                del request.session['otp_phone']
                return redirect('dashboard')
            else:
                messages.error(request, 'This phone number is not registered. Please sign up first.')
                return redirect('phone_login')
    else:
        form = PhoneOTPVerifyForm()

    return render(request, 'core/phone_verify.html', {'form': form, 'phone': phone})


def oauth_phone_capture(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if not request.session.get('oauth_sociallogin'):
        return redirect('login')

    oauth_email = request.session.get('oauth_email', '')
    oauth_name = request.session.get('oauth_name', '')

    if request.method == 'POST':
        form = PhoneLoginForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone'].strip()
            existing = User.objects.filter(phone=phone).exclude(id=request.user.id if request.user.is_authenticated else None).first()
            if existing:
                messages.error(request, 'This phone number is already associated with another account.')
                return render(request, 'core/oauth_phone_capture.html', {
                    'form': form, 'oauth_email': oauth_email, 'oauth_name': oauth_name
                })

            otp_code = f'{random.randint(0, 999999):06d}'
            PhoneOTP.objects.create(
                phone=phone,
                otp_code=otp_code,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            try:
                from .tasks import send_otp_sms
                send_otp_sms.delay(phone, otp_code)
            except Exception:
                pass

            request.session['oauth_otp_phone'] = phone
            messages.info(request, 'Verification code sent to your phone.')
            return redirect('oauth_phone_verify')
    else:
        form = PhoneLoginForm()

    return render(request, 'core/oauth_phone_capture.html', {
        'form': form, 'oauth_email': oauth_email, 'oauth_name': oauth_name
    })


def oauth_phone_verify(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    phone = request.session.get('oauth_otp_phone')
    sociallogin_data = request.session.get('oauth_sociallogin')
    if not phone or not sociallogin_data:
        return redirect('login')

    if request.method == 'POST':
        form = PhoneOTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            otp = PhoneOTP.objects.filter(
                phone=phone, is_used=False,
            ).order_by('-created_at').first()

            if not otp:
                messages.error(request, 'Code expired. Please try again.')
                return redirect('oauth_phone_capture')

            otp.attempts += 1
            otp.save(update_fields=['attempts'])

            if not otp.is_valid():
                messages.error(request, 'Code expired or too many attempts. Please try again.')
                return redirect('oauth_phone_capture')

            if otp.otp_code != code:
                messages.error(request, 'Invalid code. Please try again.')
                return render(request, 'core/oauth_phone_verify.html', {'form': form, 'phone': phone})

            otp.is_used = True
            otp.save(update_fields=['is_used'])

            request.session['oauth_verified_phone'] = phone

            from allauth.socialaccount.models import SocialLogin
            sociallogin = SocialLogin.deserialize(sociallogin_data)

            from allauth.socialaccount.helpers import complete_social_login
            response = complete_social_login(request, sociallogin)

            for key in ['oauth_sociallogin', 'oauth_email', 'oauth_name', 'oauth_otp_phone']:
                request.session.pop(key, None)

            return response
    else:
        form = PhoneOTPVerifyForm()

    return render(request, 'core/oauth_phone_verify.html', {'form': form, 'phone': phone})


def _link_person_identities_for_user(user):
    identities = PersonIdentity.objects.filter(linked_user__isnull=True)
    matching = identities.none()
    if user.email:
        matching = matching | identities.filter(email__iexact=user.email)
    if user.phone:
        matching = matching | identities.filter(phone=user.phone)

    for identity in matching:
        identity.linked_user = user
        identity.save()
        for invite in identity.group_invites.filter(is_used=False):
            existing = GroupMembership.objects.filter(
                user=user, group=invite.group
            ).first()
            if not existing:
                GroupMembership.objects.create(
                    user=user,
                    group=invite.group,
                    invited_by=invite.invited_by,
                    status='accepted',
                    person_identity=identity,
                )
            invite.is_used = True
            invite.save()

        if identity.placeholder_user:
            placeholder = identity.placeholder_user
            with transaction.atomic():
                ExpenseShare.objects.filter(user=placeholder).update(user=user)
                Payment.objects.filter(from_user=placeholder).update(from_user=user)
                Payment.objects.filter(to_user=placeholder).update(to_user=user)
                Expense.objects.filter(paid_by=placeholder).update(paid_by=user)
                Expense.objects.filter(created_by=placeholder).update(created_by=user)
                Activity.objects.filter(user=placeholder).update(user=user)
                GroupMembership.objects.filter(user=placeholder).delete()
                identity.placeholder_user = None
                identity.save()
                placeholder.delete()


@login_required
def dashboard(request):
    user = request.user
    from .currencies import format_multi_currency_balance

    memberships = GroupMembership.objects.filter(
        user=user, status='accepted'
    ).select_related('group')
    groups = [m.group for m in memberships]

    recent_activity = Activity.objects.filter(
        Q(user=user) | Q(group__in=groups)
    ).select_related('user', 'group', 'expense')[:10]

    recent_expenses = Expense.objects.filter(
        Q(group__in=groups) | Q(created_by=user)
    ).select_related('paid_by', 'group')[:5]

    balances_by_user = calculate_user_balances(user, groups)
    balance = calculate_dashboard_total_from_bilateral(balances_by_user)
    balance_display = format_multi_currency_balance(balance)

    balance_json = {k: str(v) for k, v in balance.items()}
    balances_by_user_json = []
    for item in balances_by_user:
        balances_by_user_json.append({
            'user_id': str(item['user'].id),
            'user_name': item['user'].get_display_name(),
            'balances': {k: str(v) for k, v in item['balances'].items()},
            'owed_to_user': {k: str(v) for k, v in item['owed_to_user'].items()},
            'owed_by_user': {k: str(v) for k, v in item['owed_by_user'].items()},
            'net_positive': item.get('net_positive', False),
        })

    context = {
        'groups': groups,
        'balance': balance,
        'balance_display': balance_display,
        'recent_activity': recent_activity,
        'recent_expenses': recent_expenses,
        'balances_by_user': balances_by_user,
        'balance_json': json.dumps(balance_json),
        'balances_by_user_json': json.dumps(balances_by_user_json),
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def profile(request):
    from .currencies import format_multi_currency_balance
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            remove_profile_picture = request.POST.get('remove_profile_picture', '').strip() in {'1', 'true', 'on'}
            cropped_image_data = request.POST.get('cropped_image_data', '').strip()
            if remove_profile_picture:
                try:
                    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
                    _remove_profile_picture(profile_obj)
                    messages.success(request, 'Profile picture removed successfully!')
                    return redirect('profile')
                except Exception:
                    messages.error(request, 'Could not remove profile picture. Please try again.')
                    return redirect('profile')
            if cropped_image_data:
                try:
                    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
                    image_file = _decode_cropped_profile_image(cropped_image_data)
                    _replace_profile_picture(profile_obj, image_file)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('profile')
                except Exception:
                    messages.error(request, 'Could not upload profile picture. Please try again.')
                    return redirect('profile')
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)

    user = request.user

    memberships = GroupMembership.objects.filter(
        user=user, status='accepted'
    ).select_related('group')

    groups_with_balances = []
    for m in memberships:
        balance = calculate_group_balance(user, m.group)
        groups_with_balances.append({
            'group': m.group,
            'balance': balance,
            'balance_display': format_multi_currency_balance(balance),
            'role': m.role,
        })

    total_balance = user.get_total_balance()

    context = {
        'form': form,
        'groups_with_balances': groups_with_balances,
        'total_balance': total_balance,
        'total_balance_display': format_multi_currency_balance(total_balance),
    }
    return render(request, 'core/profile.html', context)


@login_required
def profile_update_phone(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    from .forms import PhoneLoginForm
    form = PhoneLoginForm(request.POST)
    if not form.is_valid():
        errors = {k: v[0] for k, v in form.errors.items()}
        return JsonResponse({'error': errors.get('phone', 'Invalid phone number.')}, status=400)

    phone = form.cleaned_data['phone'].strip()

    existing = User.objects.filter(phone=phone).exclude(id=request.user.id).first()
    if existing:
        return JsonResponse({
            'error': 'This contact number is already registered with another account. Please enter another number.'
        }, status=400)

    otp_code = f'{random.randint(0, 999999):06d}'
    PhoneOTP.objects.create(
        phone=phone,
        otp_code=otp_code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    try:
        from .tasks import send_otp_sms
        send_otp_sms.delay(phone, otp_code)
    except Exception:
        pass

    request.session['profile_phone_update'] = phone
    return JsonResponse({'success': True, 'message': 'Verification code sent.'})


@login_required
def profile_verify_phone(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    phone = request.session.get('profile_phone_update')
    if not phone:
        return JsonResponse({'error': 'No phone update in progress.'}, status=400)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    code = data.get('otp_code', '').strip()
    if not code or len(code) != 6:
        return JsonResponse({'error': 'Please enter a valid 6-digit code.'}, status=400)

    otp = PhoneOTP.objects.filter(
        phone=phone, is_used=False,
    ).order_by('-created_at').first()

    if not otp:
        return JsonResponse({'error': 'Code expired. Please try again.'}, status=400)

    otp.attempts += 1
    otp.save(update_fields=['attempts'])

    if not otp.is_valid():
        return JsonResponse({'error': 'Code expired or too many attempts.'}, status=400)

    if otp.otp_code != code:
        return JsonResponse({'error': 'Invalid code. Please try again.'}, status=400)

    otp.is_used = True
    otp.save(update_fields=['is_used'])

    existing = User.objects.filter(phone=phone).exclude(id=request.user.id).first()
    if existing:
        return JsonResponse({
            'error': 'This contact number is already registered with another account.'
        }, status=400)

    request.user.phone = phone
    request.user.save(update_fields=['phone'])
    request.session.pop('profile_phone_update', None)

    return JsonResponse({'success': True, 'phone': phone})


@login_required
def group_list(request):
    from .currencies import format_multi_currency_balance
    memberships = GroupMembership.objects.filter(
        user=request.user, status='accepted'
    ).select_related('group')

    groups_with_balances = []
    for m in memberships:
        group = m.group
        balance = calculate_group_balance(request.user, group)
        groups_with_balances.append({
            'group': group,
            'balance': balance,
            'balance_display': format_multi_currency_balance(balance),
            'member_count': group.memberships.filter(status='accepted').count(),
            'role': m.role
        })

    context = {
        'groups': groups_with_balances,
    }
    return render(request, 'core/group_list.html', context)


@login_required
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.owner = request.user
            group.save()

            GroupMembership.objects.create(
                user=request.user,
                group=group,
                role='admin',
                status='accepted'
            )

            Activity.objects.create(
                user=request.user,
                group=group,
                action='group_created',
                description=f'Created group "{group.name}"'
            )

            messages.success(request, f'Group "{group.name}" created!')
            return redirect('group_detail', group_id=group.id)
        else:
            # Surface form errors to the user and server logs for debugging
            errors = form.errors.as_json()
            try:
                import logging
                logging.getLogger('django').warning(f'Group creation failed: {errors}')
            except Exception:
                pass
            messages.error(request, 'There were errors creating the group. Please review the form.')
    else:
        form = GroupForm()

    return render(request, 'core/group_form.html', {'form': form, 'title': 'Create Group'})


@login_required
def group_detail(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    from .currencies import format_multi_currency_balance, get_currency_symbol

    membership = GroupMembership.objects.filter(
        user=request.user, group=group, status='accepted'
    ).first()
    if not membership:
        messages.error(request, 'You are not a member of this group.')
        return redirect('group_list')

    members = []
    for m in group.memberships.filter(status='accepted').select_related('user'):
        balance = calculate_group_balance(m.user, group)
        members.append({
            'user': m.user,
            'role': m.role,
            'balance': balance,
            'balance_display': format_multi_currency_balance(balance),
            'is_placeholder': False,
        })

    placeholder_members = []
    for m in group.memberships.filter(status='placeholder').select_related('user', 'person_identity'):
        balance = calculate_group_balance(m.user, group)
        placeholder_members.append({
            'user': m.user,
            'role': m.role,
            'balance': balance,
            'balance_display': format_multi_currency_balance(balance),
            'is_placeholder': True,
            'identity': m.person_identity,
        })

    expenses_qs = group.expenses.select_related('paid_by', 'created_by').prefetch_related('shares__user').order_by('-date', '-created_at')
    payments_qs = group.payments.select_related('from_user', 'to_user').order_by('-date', '-created_at')

    # Paginate expenses and payments (10 per page)
    expenses_paginator = Paginator(expenses_qs, 10)
    payments_paginator = Paginator(payments_qs, 10)

    expenses_page_number = request.GET.get('expenses_page')
    payments_page_number = request.GET.get('payments_page')

    try:
        expenses_page = expenses_paginator.page(expenses_page_number)
    except PageNotAnInteger:
        expenses_page = expenses_paginator.page(1)
    except EmptyPage:
        expenses_page = expenses_paginator.page(expenses_paginator.num_pages)

    try:
        payments_page = payments_paginator.page(payments_page_number)
    except PageNotAnInteger:
        payments_page = payments_paginator.page(1)
    except EmptyPage:
        payments_page = payments_paginator.page(payments_paginator.num_pages)
    activity = group.activities.select_related('user')[:15]
    balance_matrix = calculate_group_balance_matrix(group)

    current_balance = calculate_group_balance(request.user, group)
    can_leave = all(abs(v) < Decimal('0.005') for v in current_balance.values()) and group.owner != request.user if current_balance else group.owner != request.user

    current_balance_json = {k: str(v) for k, v in current_balance.items()}
    members_json = []
    for m in members:
        members_json.append({
            'user_id': str(m['user'].id),
            'user_name': m['user'].get_display_name(),
            'balances': {k: str(v) for k, v in m['balance'].items()},
        })
    placeholder_members_json = []
    for m in placeholder_members:
        placeholder_members_json.append({
            'user_id': str(m['user'].id),
            'user_name': m['user'].get_display_name(),
            'balances': {k: str(v) for k, v in m['balance'].items()},
        })
    balance_matrix_json = []
    for item in balance_matrix:
        balance_matrix_json.append({
            'from_user_id': str(item['from_user'].id),
            'from_user_name': item['from_user'].get_display_name(),
            'to_user_id': str(item['to_user'].id),
            'to_user_name': item['to_user'].get_display_name(),
            'amount': str(item['amount']),
            'currency': item['currency'],
        })

    context = {
        'group': group,
        'members': members,
        'placeholder_members': placeholder_members,
        'expenses_page': expenses_page,
        'payments_page': payments_page,
        # Backwards-compat: expose plain lists for older templates/code
        'expenses': expenses_page.object_list,
        'payments': payments_page.object_list,
        'activity': activity,
        'is_admin': membership.role == 'admin',
        'balance_matrix': balance_matrix,
        'current_user_balance': current_balance,
        'current_user_balance_display': format_multi_currency_balance(current_balance),
        'can_leave': can_leave,
        'current_balance_json': json.dumps(current_balance_json),
        'members_json': json.dumps(members_json),
        'placeholder_members_json': json.dumps(placeholder_members_json),
        'balance_matrix_json': json.dumps(balance_matrix_json),
    }
    return render(request, 'core/group_detail.html', context)


@login_required
def group_edit(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    membership = GroupMembership.objects.filter(
        user=request.user, group=group, role='admin', status='accepted'
    ).first()
    if not membership:
        messages.error(request, 'Only admins can edit group settings.')
        return redirect('group_detail', group_id=group_id)

    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group updated!')
            return redirect('group_detail', group_id=group_id)
    else:
        form = GroupForm(instance=group)

    return render(request, 'core/group_form.html', {
        'form': form,
        'title': 'Edit Group',
        'group': group
    })


@login_required
def group_invite(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    membership = GroupMembership.objects.filter(
        user=request.user, group=group, status='accepted'
    ).first()
    if not membership:
        messages.error(request, 'You are not a member of this group.')
        return redirect('group_list')

    if request.method == 'POST':
        form = InviteMemberForm(request.POST)
        if form.is_valid():
            display_name = form.cleaned_data['display_name']
            channel = form.cleaned_data['channel']
            email = form.cleaned_data.get('email', '').strip()
            phone = form.cleaned_data.get('phone', '').strip()

            invited_user = None
            if channel == 'email' and email:
                invited_user = User.objects.filter(email__iexact=email).exclude(
                    email__endswith='@placeholder.splitgood.local'
                ).first()
            elif channel == 'phone' and phone:
                invited_user = User.objects.filter(phone=phone).exclude(
                    email__endswith='@placeholder.splitgood.local'
                ).first()

            if invited_user:
                existing = GroupMembership.objects.filter(
                    user=invited_user, group=group
                ).first()
                if existing:
                    messages.warning(request, f'{display_name} is already a member.')
                else:
                    GroupMembership.objects.create(
                        user=invited_user,
                        group=group,
                        invited_by=request.user,
                        status='accepted'
                    )
                    Activity.objects.create(
                        user=request.user,
                        group=group,
                        action='member_added',
                        description=f'Invited {invited_user.get_display_name()} to the group'
                    )
                    messages.success(request, f'Invitation sent to {display_name}!')
            else:
                # Unified identity logic: maintain single identity per email/contact across all groups
                with transaction.atomic():
                    # Always look for existing identity by email/contact, regardless of placeholder status
                    filter_kwargs = {'email__iexact': email} if channel == 'email' else {'phone': phone}
                    identity = PersonIdentity.objects.filter(**filter_kwargs).first()

                    # Check if already a member of this group
                    already_in_group = False
                    if identity and identity.placeholder_user:
                        already_in_group = GroupMembership.objects.filter(
                            user=identity.placeholder_user, group=group, status='placeholder'
                        ).exists()

                    if already_in_group:
                        messages.warning(request, f'{identity.display_name} has already been invited to this group.')
                    else:
                        # Create new identity if it doesn't exist
                        if not identity:
                            identity = PersonIdentity(
                                display_name=display_name,
                                email=email if channel == 'email' else None,
                                phone=phone if channel == 'phone' else None,
                                created_by=request.user,
                            )
                            identity.save()

                        # Ensure placeholder user exists (reuse if present, else create)
                        placeholder = identity.placeholder_user
                        if not placeholder:
                            placeholder_email = f'identity_{uuid.uuid4().hex[:12]}@placeholder.splitgood.local'
                            placeholder = User.objects.create_user(
                                username=placeholder_email,
                                email=placeholder_email,
                                display_name=identity.display_name,  # use identity's name, not new display_name
                                password=None,
                                is_active=False,
                                avatar_color=identity.avatar_color,
                            )
                            identity.placeholder_user = placeholder
                            identity.save()

                        # Add to this group if not already present
                        GroupMembership.objects.get_or_create(
                            user=placeholder,
                            group=group,
                            status='placeholder',
                            defaults={
                                'invited_by': request.user,
                                'person_identity': identity,
                            }
                        )

                        # Create GroupInvite record attached to this identity
                        token = str(uuid.uuid4())
                        invite = GroupInvite.objects.create(
                            group=group,
                            person_identity=identity,
                            email=email if channel == 'email' else None,
                            phone=phone if channel == 'phone' else None,
                            channel=channel,
                            invited_by=request.user,
                            token=token,
                            expires_at=timezone.now() + timedelta(days=30),
                        )

                        Activity.objects.create(
                            user=request.user,
                            group=group,
                            action='member_added',
                            description=f'Invited {identity.display_name} to the group'
                        )

                        try:
                            from .tasks import send_invite_notification
                            send_invite_notification.delay(str(invite.id))
                        except Exception:
                            pass

                        messages.success(request, f'Invitation sent to {identity.display_name}!')

            return redirect('group_detail', group_id=group_id)
    else:
        form = InviteMemberForm()

    return render(request, 'core/group_invite.html', {
        'form': form,
        'group': group
    })


@login_required
def expense_create(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    from .currencies import get_currency_symbol

    membership = GroupMembership.objects.filter(
        user=request.user, group=group, status='accepted'
    ).first()
    if not membership:
        messages.error(request, 'You are not a member of this group.')
        return redirect('group_list')

    members = list(group.get_members())

    if request.method == 'POST':
        form = ExpenseForm(group=group, data=request.POST, files=request.FILES)
        if form.is_valid():
            with transaction.atomic():
                expense = form.save(commit=False)
                expense.group = group
                expense.created_by = request.user
                expense.save()

                participants = form.cleaned_data['participants']
                split_type = expense.split_type
                total_amount = expense.total_amount

                if split_type == 'equal':
                    share_amount = total_amount / len(participants)
                    for user in participants:
                        ExpenseShare.objects.create(
                            expense=expense,
                            user=user,
                            amount_owed=share_amount.quantize(Decimal('0.01')),
                            is_paid=(user == expense.paid_by)
                        )
                else:
                    for user in participants:
                        amount_key = f'split_amount_{user.id}'
                        amount = request.POST.get(amount_key, '0')
                        try:
                            amount = Decimal(amount)
                        except:
                            amount = Decimal('0')

                        if amount > 0:
                            ExpenseShare.objects.create(
                                expense=expense,
                                user=user,
                                amount_owed=amount,
                                is_paid=(user == expense.paid_by)
                            )

                Activity.objects.create(
                    user=request.user,
                    group=group,
                    action='expense_created',
                    description=f'Added "{expense.title}" for {get_currency_symbol(expense.currency)}{expense.total_amount}',
                    expense=expense
                )

                try:
                    from .tasks import send_expense_notification
                    send_expense_notification.delay(str(expense.id))
                except Exception:
                    pass

                messages.success(request, f'Expense "{expense.title}" added!')
                return redirect('group_detail', group_id=group_id)
    else:
        form = ExpenseForm(group=group, initial={
            'date': timezone.now().date(),
            'paid_by': request.user,
            'split_type': group.default_split_type,
        })

    context = {
        'form': form,
        'group': group,
        'members': members,
    }
    return render(request, 'core/expense_form.html', context)


@login_required
def expense_detail(request, expense_id):
    expense = get_object_or_404(
        Expense.objects.select_related('group', 'paid_by', 'created_by')
        .prefetch_related('shares__user', 'comments__user'),
        id=expense_id
    )

    if expense.group:
        membership = GroupMembership.objects.filter(
            user=request.user, group=expense.group, status='accepted'
        ).first()
        if not membership:
            messages.error(request, 'You are not a member of this group.')
            return redirect('group_list')

    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.expense = expense
            comment.user = request.user
            comment.save()

            Activity.objects.create(
                user=request.user,
                group=expense.group,
                action='comment_added',
                description=f'Commented on "{expense.title}"',
                expense=expense
            )

            messages.success(request, 'Comment added!')
            return redirect('expense_detail', expense_id=expense_id)
    else:
        comment_form = CommentForm()

    context = {
        'expense': expense,
        'shares': expense.shares.select_related('user'),
        'comments': expense.comments.filter(parent__isnull=True).select_related('user'),
        'comment_form': comment_form,
    }
    return render(request, 'core/expense_detail.html', context)


@login_required
def expense_edit(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)

    if expense.created_by != request.user and not GroupMembership.objects.filter(
        user=request.user, group=expense.group, role='admin', status='accepted'
    ).exists():
        messages.error(request, 'You cannot edit this expense.')
        return redirect('expense_detail', expense_id=expense_id)

    group = expense.group
    members = list(group.get_members()) if group else []

    if request.method == 'POST':
        form = ExpenseForm(group=group, data=request.POST, files=request.FILES, instance=expense)
        if form.is_valid():
            with transaction.atomic():
                expense = form.save()

                expense.shares.all().delete()
                participants = form.cleaned_data['participants']
                split_type = expense.split_type
                total_amount = expense.total_amount

                if split_type == 'equal':
                    share_amount = total_amount / len(participants)
                    for user in participants:
                        ExpenseShare.objects.create(
                            expense=expense,
                            user=user,
                            amount_owed=share_amount.quantize(Decimal('0.01')),
                            is_paid=(user == expense.paid_by)
                        )
                else:
                    for user in participants:
                        amount_key = f'split_amount_{user.id}'
                        amount = request.POST.get(amount_key, '0')
                        try:
                            amount = Decimal(amount)
                        except:
                            amount = Decimal('0')

                        if amount > 0:
                            ExpenseShare.objects.create(
                                expense=expense,
                                user=user,
                                amount_owed=amount,
                                is_paid=(user == expense.paid_by)
                            )

                Activity.objects.create(
                    user=request.user,
                    group=group,
                    action='expense_updated',
                    description=f'Updated "{expense.title}"',
                    expense=expense
                )

                messages.success(request, 'Expense updated!')
                return redirect('expense_detail', expense_id=expense_id)
    else:
        initial_participants = [s.user for s in expense.shares.all()]
        form = ExpenseForm(group=group, instance=expense, initial={
            'participants': initial_participants
        })

    context = {
        'form': form,
        'expense': expense,
        'group': group,
        'members': members,
        'is_edit': True,
    }
    return render(request, 'core/expense_form.html', context)


@login_required
def expense_delete(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)
    group = expense.group

    if expense.created_by != request.user and not GroupMembership.objects.filter(
        user=request.user, group=group, role='admin', status='accepted'
    ).exists():
        messages.error(request, 'You cannot delete this expense.')
        return redirect('expense_detail', expense_id=expense_id)

    if request.method == 'POST':
        title = expense.title
        expense.delete()

        Activity.objects.create(
            user=request.user,
            group=group,
            action='expense_deleted',
            description=f'Deleted expense "{title}"'
        )

        messages.success(request, 'Expense deleted!')
        return redirect('group_detail', group_id=group.id)

    return render(request, 'core/expense_confirm_delete.html', {'expense': expense})


@login_required
def settle_up(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    membership = GroupMembership.objects.filter(
        user=request.user, group=group, status='accepted'
    ).first()
    if not membership:
        messages.error(request, 'You are not a member of this group.')
        return redirect('group_list')

    members = list(group.get_members())

    suggested_payments = calculate_settlements(group)

    if request.method == 'POST':
        form = PaymentForm(group=group, current_user=request.user, data=request.POST)
        if form.is_valid():
            from .currencies import get_currency_symbol
            payment = form.save(commit=False)
            payment.group = group
            payment.save()

            sym = get_currency_symbol(payment.currency)
            Activity.objects.create(
                user=request.user,
                group=group,
                action='payment_created',
                description=f'{payment.from_user.get_display_name()} settled {sym}{payment.amount} with {payment.to_user.get_display_name()}',
                payment=payment
            )

            try:
                from .tasks import send_payment_notification
                send_payment_notification.delay(str(payment.id))
            except Exception:
                pass

            messages.success(request, 'Payment recorded!')
            return redirect('group_detail', group_id=group_id)
    else:
        form = PaymentForm(group=group, current_user=request.user, initial={
            'date': timezone.now().date()
        })

    context = {
        'group': group,
        'form': form,
        'suggested_payments': suggested_payments,
        'members': members,
    }
    return render(request, 'core/settle_up.html', context)


@login_required
def activity_feed(request):
    user = request.user

    group_ids = GroupMembership.objects.filter(
        user=user, status='accepted'
    ).values_list('group_id', flat=True)

    activities = Activity.objects.filter(
        Q(user=user) | Q(group_id__in=group_ids)
    ).select_related('user', 'group', 'expense', 'payment')[:50]

    return render(request, 'core/activity_feed.html', {'activities': activities})


@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    
    membership = GroupMembership.objects.filter(
        user=request.user, group=group, status='accepted'
    ).first()
    if not membership:
        messages.error(request, 'You are not a member of this group.')
        return redirect('group_list')
    
    if group.owner == request.user:
        messages.error(request, 'Group owners cannot leave. Transfer ownership first or delete the group.')
        return redirect('group_detail', group_id=group_id)
    
    balance = calculate_group_balance(request.user, group)
    has_outstanding = any(abs(v) > Decimal('0.005') for v in balance.values()) if balance else False
    if has_outstanding:
        messages.error(request, 'You must settle all balances before leaving the group.')
        return redirect('group_detail', group_id=group_id)
    
    if request.method == 'POST':
        membership.delete()
        Activity.objects.create(
            user=request.user,
            group=group,
            action='member_removed',
            description=f'{request.user.get_display_name()} left the group'
        )
        messages.success(request, f'You have left "{group.name}".')
        return redirect('group_list')
    
    return render(request, 'core/leave_group_confirm.html', {'group': group, 'balance': balance})


# Helper functions

def calculate_group_balance(user, group):
    """Calculate a user's net balance in a specific group, per currency.

    Returns dict: {currency_code: Decimal balance}
    Positive = others owe you (net creditor)
    Negative = you owe others (net debtor)
    """
    balances = defaultdict(lambda: Decimal('0'))

    owed_to_user = ExpenseShare.objects.filter(
        expense__group=group,
        expense__paid_by=user,
    ).exclude(user=user).values('expense__currency').annotate(
        total=Sum('amount_owed')
    )
    for row in owed_to_user:
        balances[row['expense__currency']] += row['total']

    user_owes = ExpenseShare.objects.filter(
        expense__group=group,
        user=user,
    ).exclude(expense__paid_by=user).values('expense__currency').annotate(
        total=Sum('amount_owed')
    )
    for row in user_owes:
        balances[row['expense__currency']] -= row['total']

    payments_received = Payment.objects.filter(
        group=group,
        to_user=user
    ).values('currency').annotate(total=Sum('amount'))
    for row in payments_received:
        balances[row['currency']] -= row['total']

    payments_made = Payment.objects.filter(
        group=group,
        from_user=user
    ).values('currency').annotate(total=Sum('amount'))
    for row in payments_made:
        balances[row['currency']] += row['total']

    return dict({k: v for k, v in balances.items() if v != 0})


def calculate_user_balances(user, groups):
    """Compute dashboard bilateral balances from per-group outstanding edges.

    Source for dashboard aggregation is each group's settlement edge list from
    ``calculate_group_balance_matrix(group)`` where each edge means:
      from_user (debtor) ---- amount/currency ----> to_user (creditor)

    For each edge involving the logged-in user:
      - user is creditor: friend owes user   -> owed_to_user += amount
      - user is debtor:   user owes friend   -> owed_by_user += amount

    Friend channels are aggregated across all groups by friend+currency without
    subtracting inside a channel. Net (for total/ordering) is derived as
    owed_to_user - owed_by_user.
    """
    from .currencies import format_multi_currency_balance
    from .fx_service import fetch_fx_rates, detect_net_sign

    rates, _ = fetch_fx_rates('USD')

    friend_channels = defaultdict(lambda: {
        'owed_to_user': defaultdict(lambda: Decimal('0')),
        'owed_by_user': defaultdict(lambda: Decimal('0')),
    })
    user_map = {}

    for group in groups:
        for edge in calculate_group_balance_matrix(group):
            debtor = edge['from_user']
            creditor = edge['to_user']
            amount = edge['amount']
            currency = edge['currency']

            if creditor.id == user.id and debtor.id != user.id:
                # friend owes logged-in user
                friend_channels[debtor.id]['owed_to_user'][currency] += amount
                user_map[debtor.id] = debtor
            elif debtor.id == user.id and creditor.id != user.id:
                # logged-in user owes friend
                friend_channels[creditor.id]['owed_by_user'][currency] += amount
                user_map[creditor.id] = creditor

    result = []
    for friend_id, channels in friend_channels.items():
        owed_to_user = {c: v for c, v in channels['owed_to_user'].items() if v != 0}
        owed_by_user = {c: v for c, v in channels['owed_by_user'].items() if v != 0}

        currencies = set(owed_to_user.keys()) | set(owed_by_user.keys())
        net_balances = {}
        for currency in currencies:
            net = owed_to_user.get(currency, Decimal('0')) - owed_by_user.get(currency, Decimal('0'))
            if net != 0:
                net_balances[currency] = net

        if not owed_to_user and not owed_by_user:
            continue

        member = user_map.get(friend_id)
        if not member:
            continue

        sign = detect_net_sign(net_balances, rates, 'INR') if net_balances else 0

        result.append({
            'user': member,
            'balances': net_balances,
            'owed_to_user': owed_to_user,
            'owed_by_user': owed_by_user,
            'balance_display': format_multi_currency_balance(net_balances),
            'net_positive': sign > 0,
        })

    # sort largest exposure first (sum of both channels)
    result.sort(
        key=lambda x: (
            sum(abs(float(v)) for v in x['owed_to_user'].values())
            + sum(abs(float(v)) for v in x['owed_by_user'].values())
        ),
        reverse=True,
    )

    return result


def calculate_dashboard_total_from_bilateral(balances_by_user):
    """Aggregate dashboard total from bilateral channels only.

    total[currency] = sum(owed_to_user[currency]) - sum(owed_by_user[currency])
    """
    totals = defaultdict(lambda: Decimal('0'))

    for item in balances_by_user:
        for currency, amount in item.get('owed_to_user', {}).items():
            totals[currency] += amount
        for currency, amount in item.get('owed_by_user', {}).items():
            totals[currency] -= amount

    return {currency: amount for currency, amount in totals.items() if amount != 0}

def calculate_group_balance_matrix(group):
    """Calculate who owes who in a group per currency (net outstanding debts after payments)."""
    # New approach: compute net per-user balances per currency and then
    # generate a minimal set of settlement edges (no circular chains).
    members = list(group.get_members())
    from .currencies import get_currency_symbol

    # compute net balance per member per currency using existing helper
    all_balances = {}
    for member in members:
        all_balances[member] = calculate_group_balance(member, group)

    currencies = set()
    for bal in all_balances.values():
        currencies.update(bal.keys())

    simplified = []
    for currency in sorted(currencies):
        # build net mapping member -> Decimal (positive = others owe them)
        net_balances = {}
        for member in members:
            amt = all_balances.get(member, {}).get(currency, Decimal('0'))
            # ignore tiny residuals
            if abs(amt) >= Decimal('0.005'):
                net_balances[member] = amt

        if not net_balances:
            continue

        # creditors: positive amounts (others owe them), debtors: negative amounts
        creditors = [(u, b) for u, b in net_balances.items() if b > 0]
        debtors = [(u, abs(b)) for u, b in net_balances.items() if b < 0]

        # sort biggest first to minimize transactions
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)

        i, j = 0, 0
        while i < len(creditors) and j < len(debtors):
            creditor, credit = creditors[i]
            debtor, debt = debtors[j]

            amount = min(credit, debt)
            if amount > Decimal('0'):
                simplified.append({
                    'from_user': debtor,
                    'to_user': creditor,
                    'amount': amount.quantize(Decimal('0.01')),
                    'currency': currency,
                    'symbol': get_currency_symbol(currency),
                })

            credit -= amount
            debt -= amount
            creditors[i] = (creditor, credit)
            debtors[j] = (debtor, debt)

            if credit == 0:
                i += 1
            if debt == 0:
                j += 1

    return simplified


def calculate_settlements(group):
    """Calculate optimal settlement payments per currency (minimize transactions).
    
    Returns list of dicts with currency info for each suggested payment.
    """
    from .currencies import get_currency_symbol
    members = list(group.get_members())
    all_balances = {}
    for member in members:
        all_balances[member] = calculate_group_balance(member, group)

    currencies = set()
    for bal in all_balances.values():
        currencies.update(bal.keys())

    settlements = []
    for currency in sorted(currencies):
        net_balances = {}
        for member in members:
            b = all_balances.get(member, {}).get(currency, Decimal('0'))
            if b != 0:
                net_balances[member] = b

        creditors = [(u, b) for u, b in net_balances.items() if b > 0]
        debtors = [(u, abs(b)) for u, b in net_balances.items() if b < 0]

        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)

        i, j = 0, 0
        while i < len(creditors) and j < len(debtors):
            creditor, credit = creditors[i]
            debtor, debt = debtors[j]

            amount = min(credit, debt)
            if amount > 0:
                settlements.append({
                    'from_user': debtor,
                    'to_user': creditor,
                    'amount': amount.quantize(Decimal('0.01')),
                    'currency': currency,
                    'symbol': get_currency_symbol(currency),
                })

            credit -= amount
            debt -= amount
            creditors[i] = (creditor, credit)
            debtors[j] = (debtor, debt)

            if credit == 0:
                i += 1
            if debt == 0:
                j += 1

    return settlements


def get_group_currencies(group):
    """Get all currencies used in a group's expenses and payments."""
    expense_currencies = set(
        Expense.objects.filter(group=group)
        .values_list('currency', flat=True).distinct()
    )
    payment_currencies = set(
        Payment.objects.filter(group=group)
        .values_list('currency', flat=True).distinct()
    )
    return sorted(expense_currencies | payment_currencies)


@login_required
@require_GET
def api_fx_rates(request):
    base = request.GET.get('base', 'USD')
    from .fx_service import fetch_fx_rates
    rates, timestamp = fetch_fx_rates(base)
    import datetime
    ts_str = datetime.datetime.utcfromtimestamp(timestamp).strftime('%H:%M UTC')
    return JsonResponse({
        'base': base,
        'rates': rates,
        'timestamp': timestamp,
        'timestamp_display': ts_str,
    })
