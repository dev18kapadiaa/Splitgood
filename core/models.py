from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import uuid
import random
from cloudinary.models import CloudinaryField


class User(AbstractUser):
    """Extended user model with profile information"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    display_name = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    timezone = models.CharField(max_length=50, default='UTC')
    avatar_color = models.CharField(max_length=7, default='#6366f1')
    is_oauth_only = models.BooleanField(default=False)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    def get_display_name(self):
        return self.display_name or self.username or self.email.split('@')[0]
    
    def get_initials(self):
        name = self.get_display_name()
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper()

    def get_profile_image_url(self):
        profile_obj = getattr(self, 'profile', None)
        if not profile_obj or not profile_obj.image:
            return ''
        try:
            return profile_obj.image.build_url(
                width=500,
                height=500,
                crop='fill',
                fetch_format='auto',
                quality='auto',
            )
        except Exception:
            try:
                return profile_obj.image.url
            except Exception:
                return ''
    
    def get_total_balance(self):
        """Calculate total balance across all groups, per currency.
        
        Returns a dict: {currency_code: Decimal balance}
        Positive = others owe you money (net creditor)
        Negative = you owe others money (net debtor)
        """
        from collections import defaultdict
        from django.db.models import Sum

        balances = defaultdict(lambda: Decimal('0'))

        expenses = Expense.objects.prefetch_related('shares', 'contributions').all()
        for expense in expenses:
            paid = Decimal('0')
            for contribution in expense.get_contributions():
                if contribution.user_id == self.id:
                    paid += contribution.amount_paid

            share = Decimal('0')
            for share_row in expense.shares.all():
                if share_row.user_id == self.id:
                    share += share_row.amount_owed

            net = paid - share
            if net != 0:
                balances[expense.currency] += net
        
        payments_received = Payment.objects.filter(
            to_user=self
        ).values('currency').annotate(total=Sum('amount'))
        for row in payments_received:
            balances[row['currency']] -= row['total']
        
        payments_made = Payment.objects.filter(
            from_user=self
        ).values('currency').annotate(total=Sum('amount'))
        for row in payments_made:
            balances[row['currency']] += row['total']
        
        return dict({k: v for k, v in balances.items() if v != 0})


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    image = CloudinaryField('image', folder='profile_pictures', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile<{self.user.get_display_name()}>"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


AVATAR_COLORS = [
    '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f59e0b',
    '#10b981', '#06b6d4', '#3b82f6', '#a855f7', '#f97316',
]


class PersonIdentity(models.Model):
    """Tracks people invited to groups who may or may not have accounts yet.
    
    Created when someone is invited by name + email/phone.
    linked_user is set when they sign up (ForeignKey allows multiple identities per user).
    placeholder_user is the shadow User account used in the ledger before they sign up.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    linked_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='person_identities'
    )
    placeholder_user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='placeholder_identity'
    )
    avatar_color = models.CharField(max_length=7, default='#8b5cf6')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_identities'
    )
    
    class Meta:
        verbose_name_plural = 'Person identities'
    
    def save(self, *args, **kwargs):
        if not self.avatar_color or self.avatar_color == '#8b5cf6':
            self.avatar_color = random.choice(AVATAR_COLORS)
        super().save(*args, **kwargs)
    
    def get_display_name(self):
        if self.linked_user:
            return self.linked_user.get_display_name()
        return self.display_name
    
    def get_initials(self):
        name = self.get_display_name()
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper()
    
    def get_avatar_color(self):
        if self.linked_user:
            return self.linked_user.avatar_color
        return self.avatar_color
    
    def get_contact(self):
        return self.email or self.phone or ''

    @property
    def is_registered(self):
        return self.linked_user is not None
    
    def __str__(self):
        status = "registered" if self.linked_user else "unregistered"
        return f"{self.display_name} ({status})"


class Group(models.Model):
    """Expense sharing group"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)
    default_currency = models.CharField(max_length=3, default='USD')
    default_split_type = models.CharField(
        max_length=20,
        choices=[('equal', 'Equal'), ('unequal', 'Unequal'), ('percentage', 'Percentage')],
        default='equal'
    )
    group_color = models.CharField(max_length=7, default='#6366f1')
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.name
    
    def get_members(self, include_placeholders=True):
        statuses = ['accepted']
        if include_placeholders:
            statuses.append('placeholder')
        return User.objects.filter(
            group_memberships__group=self,
            group_memberships__status__in=statuses
        )
    
    def get_total_expenses(self):
        return self.expenses.aggregate(total=models.Sum('total_amount'))['total'] or Decimal('0')


class GroupMembership(models.Model):
    """Group membership with roles"""
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('admin', 'Admin'),
    ]
    STATUS_CHOICES = [
        ('accepted', 'Accepted'),
        ('placeholder', 'Placeholder'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='accepted')
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_invites')
    invited_email = models.EmailField(blank=True)
    person_identity = models.ForeignKey(
        PersonIdentity, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='memberships'
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'group']
        ordering = ['joined_at']
    
    def __str__(self):
        return f"{self.user.get_display_name()} in {self.group.name}"


class Expense(models.Model):
    """Expense record"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='expenses', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_expenses')
    paid_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paid_expenses')
    title = models.CharField(max_length=200)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    receipt_image = models.ImageField(upload_to='receipts/', blank=True, null=True)
    split_type = models.CharField(
        max_length=20,
        choices=[('equal', 'Equal'), ('unequal', 'Unequal'), ('percentage', 'Percentage')],
        default='equal'
    )
    is_settled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.title} - ${self.total_amount}"

    def get_contributions(self):
        """Return persisted contributions or fallback to legacy single payer."""
        rows = list(self.contributions.select_related('user').all())
        if rows:
            return rows
        return [
            ExpenseContribution(
                expense=self,
                user=self.paid_by,
                amount_paid=self.total_amount,
            )
        ]

    def get_paid_amount_map(self):
        paid_map = {}
        for row in self.get_contributions():
            paid_map[row.user_id] = paid_map.get(row.user_id, Decimal('0')) + row.amount_paid
        return paid_map

    def get_primary_payer(self):
        """Keep legacy UI wording by selecting the largest contributor."""
        rows = self.get_contributions()
        if not rows:
            return self.paid_by
        return max(rows, key=lambda r: r.amount_paid).user
    
    def get_payer_share(self):
        """Get the share owed by the person who paid"""
        share = self.shares.filter(user=self.paid_by).first()
        return share.amount_owed if share else Decimal('0')


class ExpenseShare(models.Model):
    """Individual share of an expense"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expense_shares')
    amount_owed = models.DecimalField(max_digits=12, decimal_places=2)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['expense', 'user']
    
    def __str__(self):
        return f"{self.user.get_display_name()} owes ${self.amount_owed} for {self.expense.title}"


class ExpenseContribution(models.Model):
    """Tracks who actually paid and how much for an expense."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='contributions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expense_contributions')
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ['expense', 'user']

    def __str__(self):
        return f"{self.user.get_display_name()} paid ${self.amount_paid} for {self.expense.title}"


class Payment(models.Model):
    """Payment/settlement between users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_made')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_received')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    method = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.from_user.get_display_name()} paid ${self.amount} to {self.to_user.get_display_name()}"


class Comment(models.Model):
    """Comment on an expense"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.user.get_display_name()} on {self.expense.title}"


class Activity(models.Model):
    """Activity log for tracking changes"""
    ACTION_CHOICES = [
        ('expense_created', 'Expense Created'),
        ('expense_updated', 'Expense Updated'),
        ('expense_deleted', 'Expense Deleted'),
        ('payment_created', 'Payment Created'),
        ('group_created', 'Group Created'),
        ('member_added', 'Member Added'),
        ('member_removed', 'Member Removed'),
        ('comment_added', 'Comment Added'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField()
    expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Activities'
    
    def __str__(self):
        return f"{self.user.get_display_name()}: {self.action}"


class GroupInvite(models.Model):
    """Pending invite for non-registered users, linked to a PersonIdentity"""
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('phone', 'Phone'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='pending_invites')
    person_identity = models.ForeignKey(
        PersonIdentity, on_delete=models.CASCADE,
        related_name='group_invites', null=True, blank=True
    )
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default='email')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_invites_sent')
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def get_contact(self):
        return self.email or self.phone or ''
    
    def __str__(self):
        contact = self.email or self.phone
        return f"Invite to {contact} for {self.group.name}"


class PhoneOTP(models.Model):
    """One-time password for phone-based and email-based verification"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=255)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        return not self.is_used and self.attempts < 5 and timezone.now() < self.expires_at

    def __str__(self):
        return f"OTP for {self.phone}"
