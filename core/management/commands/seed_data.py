from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import random

from core.models import Group, GroupMembership, Expense, ExpenseShare, Payment, Activity

User = get_user_model()

AVATAR_COLORS = ['#6366f1', '#ec4899', '#14b8a6', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#84cc16']


class Command(BaseCommand):
    help = 'Seeds the database with demo data'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database with demo data...')
        
        # Check if data already exists
        if User.objects.filter(email='alice@example.com').exists():
            self.stdout.write(self.style.WARNING('Demo data already exists. Skipping.'))
            return
        
        # Create users
        users = []
        user_data = [
            ('alice@example.com', 'Alice Johnson', '#6366f1'),
            ('bob@example.com', 'Bob Smith', '#ec4899'),
            ('charlie@example.com', 'Charlie Brown', '#14b8a6'),
            ('diana@example.com', 'Diana Ross', '#f59e0b'),
            ('evan@example.com', 'Evan Williams', '#8b5cf6'),
        ]
        
        for email, name, color in user_data:
            user = User.objects.create_user(
                username=email,
                email=email,
                password='password123',
                display_name=name,
                avatar_color=color
            )
            users.append(user)
            self.stdout.write(f'  Created user: {name}')
        
        alice, bob, charlie, diana, evan = users
        
        # Create groups
        # Group 1: Roommates
        roommates = Group.objects.create(
            name='Roommates',
            description='Shared apartment expenses with Alice, Bob, and Charlie',
            owner=alice,
            group_color='#6366f1'
        )
        
        for user in [alice, bob, charlie]:
            GroupMembership.objects.create(
                user=user,
                group=roommates,
                role='admin' if user == alice else 'member',
                status='accepted'
            )
        
        self.stdout.write(f'  Created group: Roommates')
        
        # Group 2: Trip to Paris
        paris_trip = Group.objects.create(
            name='Paris Trip 2025',
            description='Our amazing trip to Paris!',
            owner=bob,
            group_color='#ec4899',
            default_currency='EUR'
        )
        
        for user in [alice, bob, diana, evan]:
            GroupMembership.objects.create(
                user=user,
                group=paris_trip,
                role='admin' if user == bob else 'member',
                status='accepted'
            )
        
        self.stdout.write(f'  Created group: Paris Trip 2025')
        
        # Create expenses for Roommates group
        roommate_expenses = [
            ('Rent - January', Decimal('1500.00'), alice, [alice, bob, charlie], 'equal'),
            ('Groceries', Decimal('156.78'), bob, [alice, bob, charlie], 'equal'),
            ('Electricity Bill', Decimal('89.50'), charlie, [alice, bob, charlie], 'equal'),
            ('Internet', Decimal('65.00'), alice, [alice, bob, charlie], 'equal'),
            ('Cleaning Supplies', Decimal('42.35'), bob, [alice, bob, charlie], 'equal'),
        ]
        
        for title, amount, paid_by, participants, split_type in roommate_expenses:
            expense = Expense.objects.create(
                group=roommates,
                created_by=paid_by,
                paid_by=paid_by,
                title=title,
                total_amount=amount,
                split_type=split_type,
                date=timezone.now().date()
            )
            
            share_amount = amount / len(participants)
            for user in participants:
                ExpenseShare.objects.create(
                    expense=expense,
                    user=user,
                    amount_owed=share_amount.quantize(Decimal('0.01')),
                    is_paid=(user == paid_by)
                )
            
            Activity.objects.create(
                user=paid_by,
                group=roommates,
                action='expense_created',
                description=f'Added "{title}" for ${amount}',
                expense=expense
            )
        
        self.stdout.write(f'  Created {len(roommate_expenses)} expenses for Roommates')

        
        # Create expenses for Paris Trip
        paris_expenses = [
            ('Hotel (4 nights)', Decimal('850.00'), bob, [alice, bob, diana, evan], 'equal'),
            ('Eiffel Tower Tickets', Decimal('120.00'), alice, [alice, bob, diana, evan], 'equal'),
            ('Dinner at Le Jules Verne', Decimal('340.00'), diana, [alice, bob, diana, evan], 'equal'),
            ('Museum Passes', Decimal('95.00'), evan, [alice, bob, diana, evan], 'equal'),
            ('Metro Tickets', Decimal('48.00'), alice, [alice, bob, diana, evan], 'equal'),
            ('Souvenirs', Decimal('62.50'), bob, [bob, diana], 'equal'),  # Not everyone bought souvenirs
        ]
        
        for title, amount, paid_by, participants, split_type in paris_expenses:
            expense = Expense.objects.create(
                group=paris_trip,
                created_by=paid_by,
                paid_by=paid_by,
                title=title,
                total_amount=amount,
                currency='EUR',
                split_type=split_type,
                date=timezone.now().date()
            )
            
            share_amount = amount / len(participants)
            for user in participants:
                ExpenseShare.objects.create(
                    expense=expense,
                    user=user,
                    amount_owed=share_amount.quantize(Decimal('0.01')),
                    is_paid=(user == paid_by)
                )
            
            Activity.objects.create(
                user=paid_by,
                group=paris_trip,
                action='expense_created',
                description=f'Added "{title}" for ${amount}',
                expense=expense
            )
        
        self.stdout.write(f'  Created {len(paris_expenses)} expenses for Paris Trip')
        
        # Create some payments
        Payment.objects.create(
            from_user=charlie,
            to_user=alice,
            group=roommates,
            amount=Decimal('200.00'),
            date=timezone.now().date(),
            notes='Partial rent payment'
        )
        
        Activity.objects.create(
            user=charlie,
            group=roommates,
            action='payment_created',
            description=f'Charlie paid $200.00 to Alice'
        )
        
        self.stdout.write('  Created sample payment')
        
        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully!'))
        self.stdout.write('')
        self.stdout.write('Demo accounts:')
        self.stdout.write('  Email: alice@example.com, Password: password123')
        self.stdout.write('  Email: bob@example.com, Password: password123')
        self.stdout.write('  Email: charlie@example.com, Password: password123')
        self.stdout.write('  Email: diana@example.com, Password: password123')
        self.stdout.write('  Email: evan@example.com, Password: password123')
