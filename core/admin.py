from django.contrib import admin
from .models import User, Group, GroupMembership, Expense, ExpenseShare, Payment, Comment, Activity, GroupInvite


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'display_name', 'currency', 'date_joined']
    search_fields = ['email', 'display_name']
    list_filter = ['currency', 'date_joined']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'created_at', 'is_archived']
    search_fields = ['name', 'description']
    list_filter = ['is_archived', 'created_at']


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'group', 'role', 'status', 'joined_at']
    list_filter = ['role', 'status']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['title', 'total_amount', 'paid_by', 'group', 'date', 'split_type']
    search_fields = ['title', 'notes']
    list_filter = ['split_type', 'date', 'group']


@admin.register(ExpenseShare)
class ExpenseShareAdmin(admin.ModelAdmin):
    list_display = ['expense', 'user', 'amount_owed', 'is_paid']
    list_filter = ['is_paid']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['from_user', 'to_user', 'amount', 'date', 'group']
    list_filter = ['date', 'group']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['expense', 'user', 'created_at']
    search_fields = ['content']


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'group', 'created_at']
    list_filter = ['action', 'created_at']


@admin.register(GroupInvite)
class GroupInviteAdmin(admin.ModelAdmin):
    list_display = ['email', 'group', 'invited_by', 'created_at', 'is_used']
    list_filter = ['is_used', 'created_at']
