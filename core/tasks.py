from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


def _send_sms(to_phone, body):
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_PHONE_NUMBER]):
        logger.info(f"[SMS stub] To: {to_phone} | Body: {body}")
        return False
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_phone,
        )
        logger.info(f"[SMS delivered] To: {to_phone} | SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"[SMS failed] To: {to_phone} | Error: {e}")
        raise


def _send_email(subject, message, recipient_list):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(f"[Email delivered] To: {recipient_list} | Subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"[Email failed] To: {recipient_list} | Subject: {subject} | Error: {e}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_otp_sms(self, phone, otp_code):
    try:
        body = f'Your Splitgood verification code is: {otp_code}'
        success = _send_sms(phone, body)
        return success
    except Exception as exc:
        logger.warning(f"[OTP retry] Attempt {self.request.retries + 1}/3 for {phone}")
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invite_notification(self, invite_id):
    from .models import GroupInvite
    try:
        invite = GroupInvite.objects.select_related('group', 'invited_by', 'person_identity').get(id=invite_id)
    except GroupInvite.DoesNotExist:
        logger.warning(f"[Invite] GroupInvite {invite_id} not found, skipping")
        return

    group_name = invite.group.name
    inviter = invite.invited_by.get_display_name()

    try:
        if invite.channel == 'email' and invite.email:
            _send_email(
                subject=f"You're invited to join {group_name} on Splitgood",
                message=f"{inviter} invited you to join the group '{group_name}' on Splitgood. Sign up to start splitting expenses!",
                recipient_list=[invite.email],
            )
        elif invite.channel == 'phone' and invite.phone:
            _send_sms(invite.phone, f"{inviter} invited you to join '{group_name}' on Splitgood. Sign up to start splitting expenses!")
    except Exception as exc:
        logger.warning(f"[Invite retry] Attempt {self.request.retries + 1}/3 for invite {invite_id}")
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_expense_notification(self, expense_id):
    from .models import Expense
    try:
        expense = Expense.objects.select_related('group', 'paid_by').prefetch_related('shares__user').get(id=expense_id)
    except Expense.DoesNotExist:
        logger.warning(f"[Expense] Expense {expense_id} not found, skipping")
        return

    payer = expense.paid_by.get_display_name()
    for share in expense.shares.select_related('user').all():
        if share.user != expense.paid_by and share.user.email and not share.user.email.endswith('@placeholder.splitgood.local'):
            try:
                _send_email(
                    subject=f"New expense: {expense.title}",
                    message=f"{payer} added '{expense.title}' for {expense.currency} {expense.total_amount}. Your share: {expense.currency} {share.amount_owed}.",
                    recipient_list=[share.user.email],
                )
            except Exception as exc:
                logger.error(f"[Expense notification failed] User: {share.user.email} | Error: {exc}")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_notification(self, payment_id):
    from .models import Payment
    try:
        payment = Payment.objects.select_related('from_user', 'to_user', 'group').get(id=payment_id)
    except Payment.DoesNotExist:
        logger.warning(f"[Payment] Payment {payment_id} not found, skipping")
        return

    payer = payment.from_user.get_display_name()
    if payment.to_user.email and not payment.to_user.email.endswith('@placeholder.splitgood.local'):
        try:
            _send_email(
                subject=f"Payment received from {payer}",
                message=f"{payer} paid you ${payment.amount}" + (f" in {payment.group.name}" if payment.group else ""),
                recipient_list=[payment.to_user.email],
            )
        except Exception as exc:
            logger.warning(f"[Payment retry] Attempt {self.request.retries + 1}/3 for payment {payment_id}")
            self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def send_daily_balance_reminders(self):
    users = User.objects.filter(is_active=True).exclude(email='').exclude(
        email__endswith='@placeholder.splitgood.local'
    ).exclude(email__endswith='@phone.splitgood.local')

    sent_count = 0
    for user in users:
        balance = user.get_total_balance()
        if balance < 0:
            try:
                _send_email(
                    subject="Splitgood: You have outstanding balances",
                    message=f"Hi {user.get_display_name()}, you currently owe ${abs(balance):.2f} across your groups. Log in to settle up!",
                    recipient_list=[user.email],
                )
                sent_count += 1
            except Exception as exc:
                logger.error(f"[Daily reminder failed] User: {user.email} | Error: {exc}")

    logger.info(f"[Daily reminders] Sent {sent_count} reminder(s)")
    return sent_count


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def send_weekly_summary(self):
    from .models import GroupMembership, Expense, Payment
    from django.utils import timezone
    from datetime import timedelta

    one_week_ago = timezone.now() - timedelta(days=7)
    users = User.objects.filter(is_active=True).exclude(email='').exclude(
        email__endswith='@placeholder.splitgood.local'
    ).exclude(email__endswith='@phone.splitgood.local')

    sent_count = 0
    for user in users:
        group_ids = GroupMembership.objects.filter(
            user=user, status='accepted'
        ).values_list('group_id', flat=True)

        new_expenses = Expense.objects.filter(
            group_id__in=group_ids,
            created_at__gte=one_week_ago
        ).count()

        new_payments = Payment.objects.filter(
            group_id__in=group_ids,
            created_at__gte=one_week_ago
        ).count()

        if new_expenses > 0 or new_payments > 0:
            balance = user.get_total_balance()
            try:
                _send_email(
                    subject="Your Splitgood Weekly Summary",
                    message=(
                        f"Hi {user.get_display_name()},\n\n"
                        f"This week: {new_expenses} new expense(s), {new_payments} payment(s).\n"
                        f"Your net balance: ${balance:.2f}\n\n"
                        f"Log in to see details!"
                    ),
                    recipient_list=[user.email],
                )
                sent_count += 1
            except Exception as exc:
                logger.error(f"[Weekly summary failed] User: {user.email} | Error: {exc}")

    logger.info(f"[Weekly summary] Sent {sent_count} summary(s)")
    return sent_count


@shared_task
def cleanup_expired_otps():
    from .models import PhoneOTP
    from django.utils import timezone
    expired = PhoneOTP.objects.filter(expires_at__lt=timezone.now(), is_used=False)
    count = expired.count()
    expired.delete()
    logger.info(f"[OTP cleanup] Deleted {count} expired OTP(s)")
    return count
