from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect as django_redirect

User = get_user_model()


class CustomAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        if not user.username:
            user.username = user.email
        if commit:
            user.save()
        self._link_person_identities(user)
        return user

    def _link_person_identities(self, user):
        from .models import PersonIdentity, GroupMembership, GroupInvite, ExpenseShare, ExpenseContribution, Payment, Expense, Activity
        identities = PersonIdentity.objects.filter(linked_user__isnull=True)
        matching = identities.none()
        if user.email and not user.email.endswith('@placeholder.splitgood.local'):
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
                        status='accepted'
                    )
                invite.is_used = True
                invite.save()

            if identity.placeholder_user:
                placeholder = identity.placeholder_user
                with transaction.atomic():
                    ExpenseShare.objects.filter(user=placeholder).update(user=user)
                    ExpenseContribution.objects.filter(user=placeholder).update(user=user)
                    Payment.objects.filter(from_user=placeholder).update(from_user=user)
                    Payment.objects.filter(to_user=placeholder).update(to_user=user)
                    Expense.objects.filter(paid_by=placeholder).update(paid_by=user)
                    Expense.objects.filter(created_by=placeholder).update(created_by=user)
                    Activity.objects.filter(user=placeholder).update(user=user)
                    GroupMembership.objects.filter(user=placeholder).delete()
                    identity.placeholder_user = None
                    identity.save()
                    placeholder.delete()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        email = sociallogin.account.extra_data.get('email', '')
        if not email:
            return
        try:
            existing_user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            if not request.session.get('oauth_verified_phone'):
                request.session['oauth_sociallogin'] = sociallogin.serialize()
                request.session['oauth_email'] = email
                request.session['oauth_name'] = sociallogin.account.extra_data.get('name', '')
                raise ImmediateHttpResponse(django_redirect('oauth_phone_capture'))

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not user.username:
            user.username = user.email
        extra_data = sociallogin.account.extra_data
        if not user.display_name:
            user.display_name = extra_data.get('name', '')
        user.is_oauth_only = True
        phone = request.session.get('oauth_verified_phone')
        if phone:
            user.phone = phone
            request.session.pop('oauth_verified_phone', None)
        user.save()
        adapter = CustomAccountAdapter()
        adapter._link_person_identities(user)
        return user
