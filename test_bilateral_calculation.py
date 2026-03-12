#!/usr/bin/env python
"""
Test script to validate bilateral balance calculation with the given test case.
This helps identify what's wrong with the current implementation.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'splitgood.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth import get_user_model
from core.models import Group, GroupMembership, Expense, ExpenseShare, Payment
from core.views import calculate_user_balances
from decimal import Decimal

User = get_user_model()

def setup_test_data():
    """Create the Dubai-2026 test case"""
    
    # Clean up any existing test data
    Group.objects.filter(name='Dubai-2026-Test').delete()
    
    # Create users
    dev_kapadia, _ = User.objects.get_or_create(
        email='dev@example.com',
        defaults={'display_name': 'Dev Kapadia', 'username': 'dev_kapadia'}
    )
    dev_single, _ = User.objects.get_or_create(
        email='devsingle@example.com',
        defaults={'display_name': 'Dev with Single a', 'username': 'dev_single'}
    )
    sejal, _ = User.objects.get_or_create(
        email='sejal@example.com',
        defaults={'display_name': 'Sejal Manojkumar Kapadia', 'username': 'sejal'}
    )
    
    # Create group
    group = Group.objects.create(
        name='Dubai-2026-Test',
        owner=dev_kapadia,
        default_currency='USD'
    )
    
    # Add members
    GroupMembership.objects.get_or_create(user=dev_kapadia, group=group)
    GroupMembership.objects.get_or_create(user=dev_single, group=group)
    GroupMembership.objects.get_or_create(user=sejal, group=group)
    
    # Expense 1: Dev Kapadia paid 30 USD (split: Dev Single 10, Sejal 10)
    exp1 = Expense.objects.create(
        group=group,
        created_by=dev_kapadia,
        paid_by=dev_kapadia,
        title='Dinner',
        total_amount=Decimal('30'),
        currency='USD',
        split_type='equal'
    )
    ExpenseShare.objects.get_or_create(expense=exp1, user=dev_single, defaults={'amount_owed': Decimal('10')})
    ExpenseShare.objects.get_or_create(expense=exp1, user=sejal, defaults={'amount_owed': Decimal('10')})
    
    # Expense 2: Dev Kapadia paid 45 AED (split: Dev Single 15, Sejal 15)
    exp2 = Expense.objects.create(
        group=group,
        created_by=dev_kapadia,
        paid_by=dev_kapadia,
        title='Drinks',
        total_amount=Decimal('45'),
        currency='AED',
        split_type='equal'
    )
    ExpenseShare.objects.get_or_create(expense=exp2, user=dev_single, defaults={'amount_owed': Decimal('15')})
    ExpenseShare.objects.get_or_create(expense=exp2, user=sejal, defaults={'amount_owed': Decimal('15')})
    
    # Expense 3: Dev Single a paid 99 USD (split: Dev Kapadia 33, Sejal 33)
    exp3 = Expense.objects.create(
        group=group,
        created_by=dev_single,
        paid_by=dev_single,
        title='Brunch',
        total_amount=Decimal('99'),
        currency='USD',
        split_type='equal'
    )
    ExpenseShare.objects.get_or_create(expense=exp3, user=dev_kapadia, defaults={'amount_owed': Decimal('33')})
    ExpenseShare.objects.get_or_create(expense=exp3, user=sejal, defaults={'amount_owed': Decimal('33')})
    
    return group, dev_kapadia, dev_single, sejal


def print_test_results(user, his_name, expected_balances):
    """Print bilateral balance calculation results for a user"""
    from core.models import Group, GroupMembership
    
    memberships = GroupMembership.objects.filter(user=user, status='accepted').select_related('group')
    groups = [m.group for m in memberships]
    
    print(f"\n{'='*60}")
    print(f"📊 {his_name}'s Dashboard")
    print(f"{'='*60}")
    
    balances_result = calculate_user_balances(user, groups)
    
    print(f"\n✅ Expected Results:")
    for friend_name, expected_balance in expected_balances.items():
        print(f"  {friend_name}: {expected_balance}")
    
    print(f"\n📈 Actual Results:")
    for item in balances_result:
        friend_name = item['user'].get_display_name()
        balance = item['balances']
        owed_to_user = item.get('owed_to_user', {})
        owed_by_user = item.get('owed_by_user', {})
        
        # Format the balance for display
        balance_str = ' | '.join([
            ' '.join([f"{v:+.2f} {k}" for k, v in balance.items()])
        ])
        
        print(f"  {friend_name}: {balance_str}")
        print(f"    owed_to_user: {owed_to_user}")
        print(f"    owed_by_user: {owed_by_user}")
        print(f"    net_positive: {item.get('net_positive', False)}")
    
    # Check if matches expected
    print(f"\n🔍 Validation:")
    matches = True
    for item in balances_result:
        friend_name = item['user'].get_display_name()
        if friend_name in expected_balances:
            expected = expected_balances[friend_name]
            actual = item['balances']
            # Check if all values match (ignoring zero-value currencies)
            actual_nonzero = {k: v for k, v in actual.items() if v != 0}
            expected_nonzero = {k: v for k, v in expected.items() if v != 0}
            
            if actual_nonzero == expected_nonzero:
                print(f"  ✓ {friend_name}: MATCHES")
            else:
                print(f"  ✗ {friend_name}: MISMATCH")
                print(f"    Expected (non-zero): {expected_nonzero}")
                print(f"    Actual (non-zero): {actual_nonzero}")
                matches = False
        else:
            print(f"  ? {friend_name}: NOT IN EXPECTED")
            matches = False
    
    return balances_result


if __name__ == '__main__':
    print("🧪 Testing Bilateral Balance Calculation")
    print("=" * 60)
    
    group, dev_kapadia, dev_single, sejal = setup_test_data()
    
    print(f"\n✅ Test Data Created:")
    print(f"  Group: {group.name}")
    print(f"  Members: {dev_kapadia.get_display_name()}, {dev_single.get_display_name()}, {sejal.get_display_name()}")
    
    # Test 1: Dev Kapadia's perspective
    expected_dev_kapadia = {
        'Dev with Single a': {'USD': Decimal('-23'), 'AED': Decimal('15')},
        'Sejal Manojkumar Kapadia': {'USD': Decimal('10'), 'AED': Decimal('15')},
    }
    print_test_results(dev_kapadia, "Dev Kapadia", expected_dev_kapadia)
    
    # Test 2: Dev Single a's perspective
    expected_dev_single = {
        'Dev Kapadia': {'USD': Decimal('23'), 'AED': Decimal('-15')},
        'Sejal Manojkumar Kapadia': {'USD': Decimal('33'), 'AED': Decimal('0')},
    }
    print_test_results(dev_single, "Dev Single a", expected_dev_single)
    
    # Test 3: Sejal's perspective
    expected_sejal = {
        'Dev Kapadia': {'USD': Decimal('-10'), 'AED': Decimal('-15')},
        'Dev with Single a': {'USD': Decimal('-33'), 'AED': Decimal('0')},
    }
    sejal_results = print_test_results(sejal, "Sejal Manojkumar Kapadia", expected_sejal)

    # ---------- additional scenario tests ----------
    def setup_extra_scenarios(dev, single, sejal):
        """Create additional groups to exercise edge cases described in the
        requirement document."""
        extra_groups = []

        # selective / unequal split + payment
        g2 = Group.objects.create(name='Selective-Test', owner=dev, default_currency='USD')
        for u in (dev, single, sejal):
            GroupMembership.objects.get_or_create(user=u, group=g2)
        # dev_single pays 120 USD, dev owes 50, sejal owes 70
        exp4 = Expense.objects.create(
            group=g2, created_by=single, paid_by=single,
            title='Selective bill', total_amount=Decimal('120'), currency='USD', split_type='unequal'
        )
        ExpenseShare.objects.get_or_create(expense=exp4, user=dev, defaults={'amount_owed': Decimal('50')})
        ExpenseShare.objects.get_or_create(expense=exp4, user=sejal, defaults={'amount_owed': Decimal('70')})
        # payment partially settles dev's debt
        Payment.objects.create(group=g2, from_user=dev, to_user=single, amount=Decimal('30'), currency='USD')
        extra_groups.append(g2)

        # mutual equal debts
        g3 = Group.objects.create(name='Mutual-Test', owner=dev, default_currency='USD')
        for u in (dev, single, sejal):
            GroupMembership.objects.get_or_create(user=u, group=g3)
        exp5 = Expense.objects.create(
            group=g3, created_by=dev, paid_by=dev,
            title='A pays B', total_amount=Decimal('50'), currency='USD', split_type='equal'
        )
        ExpenseShare.objects.get_or_create(expense=exp5, user=single, defaults={'amount_owed': Decimal('50')})
        exp6 = Expense.objects.create(
            group=g3, created_by=single, paid_by=single,
            title='B pays A', total_amount=Decimal('75'), currency='USD', split_type='equal'
        )
        ExpenseShare.objects.get_or_create(expense=exp6, user=dev, defaults={'amount_owed': Decimal('75')})
        extra_groups.append(g3)

        # fully settled
        g4 = Group.objects.create(name='Settled-Test', owner=dev, default_currency='USD')
        GroupMembership.objects.get_or_create(user=dev, group=g4)
        GroupMembership.objects.get_or_create(user=single, group=g4)
        exp7 = Expense.objects.create(
            group=g4, created_by=dev, paid_by=dev,
            title='One-time', total_amount=Decimal('20'), currency='USD', split_type='equal'
        )
        ExpenseShare.objects.get_or_create(expense=exp7, user=single, defaults={'amount_owed': Decimal('20')})
        Payment.objects.create(group=g4, from_user=single, to_user=dev, amount=Decimal('20'), currency='USD')
        extra_groups.append(g4)

        return extra_groups

    extras = setup_extra_scenarios(dev_kapadia, dev_single, sejal)
    print("\n🔧 Running additional scenario tests across multiple groups")
    all_groups = [group] + extras
    for person, name in [(dev_kapadia, 'Dev Kapadia'), (dev_single, "Dev Single a"), (sejal, 'Sejal')]:
        print_test_results(person, name, {})  # we don't have hardcoded expected values here

    print(f"\n{'='*60}")
    print("✅ SYMMETRY AND TOTAL VALIDATION")
    print(f"{'='*60}")
    
    # Verify Symmetry Rule: For any pair A and B, Net(A,B) = -Net(B,A)
    print(f"\n🔄 Symmetry Rule Verification: Net(A,B) = -Net(B,A)")
    
    # re-run symmetry checks over the original + extra groups (if any)
    groups_for_validation = [group] + (extras if 'extras' in locals() else [])
    dev_kap_results = calculate_user_balances(dev_kapadia, groups_for_validation)
    dev_single_results = calculate_user_balances(dev_single, groups_for_validation)
    sejal_results = calculate_user_balances(sejal, groups_for_validation)
    
    # Create maps for easier lookup
    kap_vs_others = {r['user'].id: r['balances'] for r in dev_kap_results}
    single_vs_others = {r['user'].id: r['balances'] for r in dev_single_results}
    sejal_vs_others = {r['user'].id: r['balances'] for r in sejal_results}
    
    def validate_symmetry(user_a_id, name_a, balances_a, user_b_id, name_b, balances_b):
        """Check if Net(A,B) = -Net(B,A)"""
        a_to_b = balances_a.get(user_b_id, {})
        b_to_a = balances_b.get(user_a_id, {})
        
        all_currencies = set(a_to_b.keys()) | set(b_to_a.keys())
        
        symmetric = True
        for curr in all_currencies:
            a_val = a_to_b.get(curr, Decimal('0'))
            b_val = b_to_a.get(curr, Decimal('0'))
            if a_val + b_val != 0:
                symmetric = False
                print(f"  ✗ {name_a} vs {name_b} ({curr}): {a_val} + {b_val} != 0")
            else:
                print(f"  ✓ {name_a} vs {name_b} ({curr}): {a_val} ↔ {b_val}")
        
        return symmetric
    
    validate_symmetry(dev_kapadia.id, 'Dev Kapadia', kap_vs_others, dev_single.id, 'Dev Single a', single_vs_others)
    validate_symmetry(dev_kapadia.id, 'Dev Kapadia', kap_vs_others, sejal.id, 'Sejal', sejal_vs_others)
    validate_symmetry(dev_single.id, 'Dev Single a', single_vs_others, sejal.id, 'Sejal', sejal_vs_others)
    
    print(f"\n{'='*60}")
    print("✅ Test suite completed!")
