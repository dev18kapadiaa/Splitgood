from django.db import migrations


def cleanup_fake_email_accounts(apps, schema_editor):
    User = apps.get_model('core', 'User')
    ExpenseShare = apps.get_model('core', 'ExpenseShare')
    Payment = apps.get_model('core', 'Payment')
    Expense = apps.get_model('core', 'Expense')
    Activity = apps.get_model('core', 'Activity')
    GroupMembership = apps.get_model('core', 'GroupMembership')

    fake_users = User.objects.filter(email__endswith='@phone.splitgood.local')
    for user in fake_users:
        has_expenses = ExpenseShare.objects.filter(user=user).exists()
        has_payments_made = Payment.objects.filter(from_user=user).exists()
        has_payments_received = Payment.objects.filter(to_user=user).exists()
        has_created_expenses = Expense.objects.filter(created_by=user).exists()
        has_paid_expenses = Expense.objects.filter(paid_by=user).exists()

        if not any([has_expenses, has_payments_made, has_payments_received, has_created_expenses, has_paid_expenses]):
            GroupMembership.objects.filter(user=user).delete()
            Activity.objects.filter(user=user).delete()
            user.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_add_is_oauth_only_remove_pending_status'),
    ]

    operations = [
        migrations.RunPython(cleanup_fake_email_accounts, migrations.RunPython.noop),
    ]
