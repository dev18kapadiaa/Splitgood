from django.test import TestCase, override_settings
from django.urls import reverse
import json
from decimal import Decimal

from core.fx_service import fetch_fx_rates, compute_unified_balance
from core.models import User, Group, GroupMembership, Expense, ExpenseShare, PersonIdentity

# Create your tests here.

class FXServiceTests(TestCase):
    def test_rates_contain_aed_inr(self):
        rates, ts = fetch_fx_rates('USD')
        # ensure our primary provider supports required currencies
        self.assertIn('AED', rates)
        self.assertIn('INR', rates)
        self.assertGreater(rates['AED'], 0)
        self.assertGreater(rates['INR'], 0)

    def test_compute_unified_balance(self):
        rates, ts = fetch_fx_rates('USD')
        balances = {'USD': '10', 'AED': '20'}
        val = compute_unified_balance(balances, 'USD', rates)
        # should be numeric and not equal to simple sum
        self.assertIsInstance(val, float)
        self.assertNotEqual(val, 30.0)

    @override_settings(EXCHANGE_RATE_API_KEY=None)
    def test_fallback_provider_used_when_no_key(self):
        # even without a key we should still get a sane rate map from one of
        # the legacy providers.  at minimum the base currency must be present
        # and the map should contain more than one entry.
        rates, ts = fetch_fx_rates('USD')
        self.assertIn('USD', rates)
        self.assertGreater(len(rates), 1)

class GroupDetailViewTests(TestCase):
    def setUp(self):
        # create two users
        self.user1 = User.objects.create_user('user1', 'user1@example.com', 'pass')
        self.user2 = User.objects.create_user('user2', 'user2@example.com', 'pass')

    def test_placeholder_members_json(self):
        group = Group.objects.create(name='TestGroup', owner=self.user1)
        GroupMembership.objects.create(user=self.user1, group=group, status='accepted', role='member')
        GroupMembership.objects.create(user=self.user2, group=group, status='placeholder', role='member')
        self.client.force_login(self.user1)
        url = reverse('group_detail', args=[group.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('placeholder_members_json', resp.context)
        data = json.loads(resp.context['placeholder_members_json'])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['user_id'], str(self.user2.id))

    def test_dashboard_shows_bilateral_rows_when_total_zero(self):
        # setup group with circular debts such that overall balance for user1 is zero
        # but bilateral friend channels still exist and must be shown
        user3 = User.objects.create_user('user3', 'u3@example.com', 'pass')
        group = Group.objects.create(name='Circ', owner=self.user1)
        # accept all members
        for u in (self.user1, self.user2, user3):
            GroupMembership.objects.create(user=u, group=group, status='accepted', role='member')
        # user1 lends 50 to user2
        exp1 = Expense.objects.create(group=group, created_by=self.user1, paid_by=self.user1,
                               title='u1->u2', total_amount=50, currency='USD')
        ExpenseShare.objects.create(expense=exp1, user=self.user2, amount_owed=50)
        # user2 lends 50 to user3
        exp2 = Expense.objects.create(group=group, created_by=self.user2, paid_by=self.user2,
                               title='u2->u3', total_amount=50, currency='USD')
        ExpenseShare.objects.create(expense=exp2, user=user3, amount_owed=50)
        # user3 lends 50 to user1
        exp3 = Expense.objects.create(group=group, created_by=user3, paid_by=user3,
                               title='u3->u1', total_amount=50, currency='USD')
        ExpenseShare.objects.create(expense=exp3, user=self.user1, amount_owed=50)

        self.client.force_login(self.user1)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        # balance should be zero
        self.assertEqual(resp.context['balance'], {})
        # no outstanding bilateral edge involving user1 remains
        self.assertEqual(resp.context['balances_by_user'], [])

    def test_dashboard_aggregates_friend_balances(self):
        """Verify dashboard shows one aggregated entry per friend across all two‑member groups.
        (multi‑member groups are covered by a separate test below.)"""
        user3 = User.objects.create_user('user3', 'u3@example.com', 'pass')
        group1 = Group.objects.create(name='Group1', owner=self.user1)
        group2 = Group.objects.create(name='Group2', owner=self.user1)
        for g in (group1, group2):
            GroupMembership.objects.create(user=self.user1, group=g, status='accepted', role='member')
            GroupMembership.objects.create(user=user3, group=g, status='accepted', role='member')

        # Group1: user3 paid $43 for user1, so user1 owes user3 $43
        exp1 = Expense.objects.create(group=group1, created_by=user3, paid_by=user3,
                                       title='u3->u1', total_amount=43, currency='USD')
        ExpenseShare.objects.create(expense=exp1, user=self.user1, amount_owed=43)
        
        # Group2: user1 paid $53 for user3, so user3 owes user1 $53
        exp2 = Expense.objects.create(group=group2, created_by=self.user1, paid_by=self.user1,
                                       title='u1->u3', total_amount=53, currency='USD')
        ExpenseShare.objects.create(expense=exp2, user=user3, amount_owed=53)

        self.client.force_login(self.user1)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        balances = resp.context['balances_by_user']
        
        # Should have 1 entry (aggregated across both groups)
        self.assertEqual(len(balances), 1)
        
        entry = balances[0]
        self.assertEqual(entry['user'].id, user3.id)
        
        # Aggregate: user1 owes $43 in group1, user3 owes user1 $53 in group2
        # From user1's perspective: -43 + 53 = +10 (user3 owes user1)
        self.assertEqual(entry['balances']['USD'], Decimal('10'))
        self.assertTrue(entry['net_positive'])  # user3 owes user1

        # channel split must remain separate in dashboard data
        self.assertEqual(entry['owed_to_user'], {'USD': Decimal('53.00')})
        self.assertEqual(entry['owed_by_user'], {'USD': Decimal('43.00')})
        
        # Should not have 'group' key (it's aggregated)
        self.assertNotIn('group', entry)

    def test_dashboard_pairwise_three_person_group(self):
        """3‑member group: balance should only appear for actual pairwise debts.

        For a single INR expense of 300 paid by user3 split evenly between
        user1 (logged in), user2, and user3, user1 and user2 both owe user3
        ₹100 and should not owe each other.  The dashboard should therefore
        show an entry for user3 only and not for user2 when logged in as
        user1.  Signs should correspond to the logged‑in user's perspective.
        """
        user2 = User.objects.create_user('user2b', 'u2b@example.com', 'pass')
        user3 = User.objects.create_user('user3b', 'u3b@example.com', 'pass')
        group = Group.objects.create(name='ThreeWay', owner=self.user1)
        for u in (self.user1, user2, user3):
            GroupMembership.objects.create(user=u, group=group, status='accepted', role='member')

        # user3 pays 300 INR split evenly across three people
        exp = Expense.objects.create(group=group, created_by=user3, paid_by=user3,
                                     title='group expense', total_amount=300, currency='INR')
        for u in (self.user1, user2, user3):
            ExpenseShare.objects.create(expense=exp, user=u, amount_owed=Decimal('100'))

        self.client.force_login(self.user1)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        balances = {item['user'].id: item for item in resp.context['balances_by_user']}

        # user2 should not appear because user1 and user2 have no direct debt
        self.assertNotIn(user2.id, balances)

        # user3 should appear with negative ₹100 (user1 owes user3)
        self.assertIn(user3.id, balances)
        entry = balances[user3.id]
        self.assertEqual(entry['balances']['INR'], Decimal('-100'))
        self.assertFalse(entry['net_positive'])
        # mixed currency case should split correctly
        self.assertEqual(entry['owed_to_user'], {})
        self.assertEqual(entry['owed_by_user'], {'INR': Decimal('100')})

    def test_dashboard_ignores_empty_groups(self):
        """If the user belongs to a group with no activity the dashboard should
        simply ignore it and not create spurious friend entries."""
        friend = User.objects.create_user('friend', 'f@example.com', 'pass')
        # group1 has an expense, group2 is empty
        group1 = Group.objects.create(name='Active', owner=self.user1)
        group2 = Group.objects.create(name='Empty', owner=self.user1)
        for g in (group1, group2):
            GroupMembership.objects.create(user=self.user1, group=g, status='accepted', role='member')
            GroupMembership.objects.create(user=friend, group=g, status='accepted', role='member')

        # add a single USD expense in group1 paid by friend for user1
        exp = Expense.objects.create(group=group1, created_by=friend, paid_by=friend,
                                     title='expense', total_amount=20, currency='USD')
        ExpenseShare.objects.create(expense=exp, user=self.user1, amount_owed=20)

        self.client.force_login(self.user1)
        resp = self.client.get(reverse('dashboard'))
        balances = resp.context['balances_by_user']
        # should only have one entry for friend and no sign of the empty group
        self.assertEqual(len(balances), 1)
        entry = balances[0]
        self.assertEqual(entry['user'].id, friend.id)
        self.assertEqual(entry['balances'], {'USD': Decimal('-20')})
        self.assertEqual(entry['owed_by_user'], {'USD': Decimal('20')})
        self.assertEqual(entry['owed_to_user'], {})


class DashboardBilateralRuleTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user('me', 'me@example.com', 'pass')
        self.a = User.objects.create_user('frienda', 'a@example.com', 'pass')
        self.b = User.objects.create_user('friendb', 'b@example.com', 'pass')
        self.user1 = self.me
        self.user2 = self.a

    def _group(self, name, members):
        group = Group.objects.create(name=name, owner=self.me)
        for member in members:
            GroupMembership.objects.create(user=member, group=group, status='accepted', role='member')
        return group

    def _dashboard_balances(self):
        self.client.force_login(self.me)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        return resp.context['balances_by_user'], resp.context['balance']

    def test_1_single_group_single_currency(self):
        group = self._group('G1', [self.me, self.a])
        exp = Expense.objects.create(
            group=group, created_by=self.me, paid_by=self.me,
            title='single', total_amount=25, currency='AED'
        )
        ExpenseShare.objects.create(expense=exp, user=self.a, amount_owed=25)

        balances, total = self._dashboard_balances()
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]['owed_to_user'], {'AED': Decimal('25')})
        self.assertEqual(total, {'AED': Decimal('25')})

    def test_2_multiple_groups_same_friend_same_currency_merge(self):
        g1 = self._group('G1', [self.me, self.a])
        g2 = self._group('G2', [self.me, self.a])

        e1 = Expense.objects.create(group=g1, created_by=self.me, paid_by=self.me, title='e1', total_amount=15, currency='AED')
        e2 = Expense.objects.create(group=g2, created_by=self.me, paid_by=self.me, title='e2', total_amount=10, currency='AED')
        ExpenseShare.objects.create(expense=e1, user=self.a, amount_owed=15)
        ExpenseShare.objects.create(expense=e2, user=self.a, amount_owed=10)

        balances, total = self._dashboard_balances()
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]['owed_to_user'], {'AED': Decimal('25')})
        self.assertEqual(total, {'AED': Decimal('25')})

    def test_3_multiple_groups_same_friend_multiple_currencies(self):
        g1 = self._group('G1', [self.me, self.a])
        g2 = self._group('G2', [self.me, self.a])

        e1 = Expense.objects.create(group=g1, created_by=self.me, paid_by=self.me, title='e1', total_amount=25, currency='AED')
        e2 = Expense.objects.create(group=g2, created_by=self.a, paid_by=self.a, title='e2', total_amount=13, currency='USD')
        ExpenseShare.objects.create(expense=e1, user=self.a, amount_owed=25)
        ExpenseShare.objects.create(expense=e2, user=self.me, amount_owed=13)

        balances, total = self._dashboard_balances()
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]['owed_to_user'], {'AED': Decimal('25')})
        self.assertEqual(balances[0]['owed_by_user'], {'USD': Decimal('13')})
        self.assertEqual(total, {'AED': Decimal('25'), 'USD': Decimal('-13')})

        rates = {'AED': 22.0, 'USD': 83.0, 'INR': 1.0}
        owed_you_inr = 25.0 / rates['AED'] * rates['INR']
        you_owe_inr = 13.0 / rates['USD'] * rates['INR']
        self.assertGreater(owed_you_inr, 0)
        self.assertGreater(you_owe_inr, 0)

    def test_4_friend_only_you_owe(self):
        group = self._group('G1', [self.me, self.a])
        exp = Expense.objects.create(group=group, created_by=self.a, paid_by=self.a, title='e1', total_amount=13, currency='USD')
        ExpenseShare.objects.create(expense=exp, user=self.me, amount_owed=13)

        balances, total = self._dashboard_balances()
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]['owed_to_user'], {})
        self.assertEqual(balances[0]['owed_by_user'], {'USD': Decimal('13')})
        self.assertEqual(total, {'USD': Decimal('-13')})

    def test_5_friend_only_owes_you(self):
        group = self._group('G1', [self.me, self.a])
        exp = Expense.objects.create(group=group, created_by=self.me, paid_by=self.me, title='e1', total_amount=10, currency='AED')
        ExpenseShare.objects.create(expense=exp, user=self.a, amount_owed=10)

        balances, total = self._dashboard_balances()
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]['owed_to_user'], {'AED': Decimal('10')})
        self.assertEqual(balances[0]['owed_by_user'], {})
        self.assertEqual(total, {'AED': Decimal('10')})

    def test_6_total_balance_multi_currency_evaluation(self):
        g1 = self._group('G1', [self.me, self.a])
        g2 = self._group('G2', [self.me, self.a])
        g3 = self._group('G3', [self.me, self.b])

        e1 = Expense.objects.create(group=g1, created_by=self.me, paid_by=self.me, title='e1', total_amount=30, currency='AED')
        e2 = Expense.objects.create(group=g2, created_by=self.a, paid_by=self.a, title='e2', total_amount=13, currency='USD')
        e3 = Expense.objects.create(group=g3, created_by=self.me, paid_by=self.me, title='e3', total_amount=20, currency='USD')
        ExpenseShare.objects.create(expense=e1, user=self.a, amount_owed=30)
        ExpenseShare.objects.create(expense=e2, user=self.me, amount_owed=13)
        ExpenseShare.objects.create(expense=e3, user=self.b, amount_owed=20)

        _, total = self._dashboard_balances()
        self.assertEqual(total, {'AED': Decimal('30'), 'USD': Decimal('7')})

        rates = {'AED': 22.0, 'USD': 83.0, 'INR': 1.0}
        unified = (30.0 / rates['AED'] * rates['INR']) + (7.0 / rates['USD'] * rates['INR'])
        self.assertGreater(unified, 0)

    def test_7_toggle_on_off_raw_data_is_reversible(self):
        group = self._group('G1', [self.me, self.a])
        e1 = Expense.objects.create(group=group, created_by=self.me, paid_by=self.me, title='e1', total_amount=25, currency='AED')
        e2 = Expense.objects.create(group=group, created_by=self.a, paid_by=self.a, title='e2', total_amount=13, currency='USD')
        ExpenseShare.objects.create(expense=e1, user=self.a, amount_owed=25)
        ExpenseShare.objects.create(expense=e2, user=self.me, amount_owed=13)

        raw_balances_1, raw_total_1 = self._dashboard_balances()
        raw_balances_2, raw_total_2 = self._dashboard_balances()

        self.assertEqual(raw_total_1, raw_total_2)
        self.assertEqual(raw_balances_1[0]['owed_to_user'], raw_balances_2[0]['owed_to_user'])
        self.assertEqual(raw_balances_1[0]['owed_by_user'], raw_balances_2[0]['owed_by_user'])

    def test_unified_identity_same_email_multiple_groups(self):
        '''Test that inviting same email to multiple groups maintains single identity'''
        group1 = Group.objects.create(name='Group1', owner=self.user1)
        group2 = Group.objects.create(name='Group2', owner=self.user1)
        
        for g in (group1, group2):
            GroupMembership.objects.create(user=self.user1, group=g, status='accepted', role='admin')
        
        self.client.force_login(self.user1)
        
        # First invitation to email X in group1 with name "Alice"
        resp1 = self.client.post(reverse('group_invite', args=[group1.id]), {
            'display_name': 'Alice',
            'channel': 'email',
            'email': 'alice@example.com',
        })
        self.assertEqual(resp1.status_code, 302)
        
        # Verify identity and placeholder created
        identity1 = PersonIdentity.objects.filter(email__iexact='alice@example.com').first()
        self.assertIsNotNone(identity1)
        self.assertEqual(identity1.display_name, 'Alice')
        placeholder1 = identity1.placeholder_user
        self.assertIsNotNone(placeholder1)
        
        # Verify membership in group1
        group1_membership = GroupMembership.objects.filter(
            user=placeholder1, group=group1, status='placeholder'
        ).exists()
        self.assertTrue(group1_membership)
        
        # Second invitation to same email in group2 with different name "Alicia"
        resp2 = self.client.post(reverse('group_invite', args=[group2.id]), {
            'display_name': 'Alicia',  # different name
            'channel': 'email',
            'email': 'alice@example.com',  # same email
        })
        self.assertEqual(resp2.status_code, 302)
        
        # Verify same identity is reused
        identity2 = PersonIdentity.objects.filter(email__iexact='alice@example.com').first()
        self.assertEqual(identity1.id, identity2.id)  # same identity
        self.assertEqual(identity2.display_name, 'Alice')  # original name preserved
        
        # Verify same placeholder is reused
        placeholder2 = identity2.placeholder_user
        self.assertEqual(placeholder1.id, placeholder2.id)  # same placeholder user
        
        # Verify membership in both groups
        group1_membership = GroupMembership.objects.filter(
            user=placeholder2, group=group1, status='placeholder'
        ).exists()
        self.assertTrue(group1_membership)
        
        group2_membership = GroupMembership.objects.filter(
            user=placeholder2, group=group2, status='placeholder'
        ).exists()
        self.assertTrue(group2_membership)
        
        # Verify no duplicate placeholder users
        placeholder_count = User.objects.filter(
            email__startswith='identity_',
            email__endswith='@placeholder.splitgood.local'
        ).count()
        self.assertEqual(placeholder_count, 1)  # only one placeholder for this identity

    def test_unified_identity_duplicate_invitation_same_group(self):
        '''Test that inviting same email to same group twice shows warning'''
        group = Group.objects.create(name='TestGroup', owner=self.user1)
        GroupMembership.objects.create(user=self.user1, group=group, status='accepted', role='admin')
        
        self.client.force_login(self.user1)
        
        # First invitation
        resp1 = self.client.post(reverse('group_invite', args=[group.id]), {
            'display_name': 'Bob',
            'channel': 'email',
            'email': 'bob@example.com',
        })
        self.assertEqual(resp1.status_code, 302)
        
        # Second invitation to same email in same group
        resp2 = self.client.post(reverse('group_invite', args=[group.id]), {
            'display_name': 'Bob',
            'channel': 'email',
            'email': 'bob@example.com',
        })
        self.assertEqual(resp2.status_code, 302)
        
        # Check that warning was shown
        messages_list = list(resp2.wsgi_request._messages)
        warning_found = any('already been invited' in str(m) for m in messages_list)
        self.assertTrue(warning_found)

    def test_unified_identity_phone_channel(self):
        '''Test unified identity works with phone channel too'''
        group1 = Group.objects.create(name='Group1', owner=self.user1)
        group2 = Group.objects.create(name='Group2', owner=self.user1)
        
        for g in (group1, group2):
            GroupMembership.objects.create(user=self.user1, group=g, status='accepted', role='admin')
        
        self.client.force_login(self.user1)
        
        # First invitation via phone
        resp1 = self.client.post(reverse('group_invite', args=[group1.id]), {
            'display_name': 'Charlie',
            'channel': 'phone',
            'phone': '+1234567890',
        })
        self.assertEqual(resp1.status_code, 302)
        
        identity1 = PersonIdentity.objects.filter(phone='+1234567890').first()
        self.assertIsNotNone(identity1)
        self.assertEqual(identity1.display_name, 'Charlie')
        
        # Second invitation same phone, different group
        resp2 = self.client.post(reverse('group_invite', args=[group2.id]), {
            'display_name': 'Charles',  # different name
            'channel': 'phone',
            'phone': '+1234567890',  # same phone
        })
        self.assertEqual(resp2.status_code, 302)
        
        # Verify same identity reused, name preserved
        identity2 = PersonIdentity.objects.filter(phone='+1234567890').first()
        self.assertEqual(identity1.id, identity2.id)
        self.assertEqual(identity2.display_name, 'Charlie')  # original preserved
    def test_dashboard_ignores_empty_groups(self):
        """If the user belongs to a group with no activity the dashboard should
        simply ignore it and not create spurious friend entries.
        """
        friend = User.objects.create_user('friend', 'f@example.com', 'pass')
        # group1 has an expense, group2 is empty
        group1 = Group.objects.create(name='Active', owner=self.user1)
        group2 = Group.objects.create(name='Empty', owner=self.user1)
        for g in (group1, group2):
            GroupMembership.objects.create(user=self.user1, group=g, status='accepted', role='member')
            GroupMembership.objects.create(user=friend, group=g, status='accepted', role='member')

        # add a single USD expense in group1 paid by friend for user1
        exp = Expense.objects.create(group=group1, created_by=friend, paid_by=friend,
                                     title='expense', total_amount=20, currency='USD')
        ExpenseShare.objects.create(expense=exp, user=self.user1, amount_owed=20)

        self.client.force_login(self.user1)
        resp = self.client.get(reverse('dashboard'))
        balances = resp.context['balances_by_user']
        # should only have one entry for friend and no sign of the empty group
        self.assertEqual(len(balances), 1)
        entry = balances[0]
        self.assertEqual(entry['user'].id, friend.id)
        self.assertEqual(entry['balances'], {'USD': Decimal('-20')})
        self.assertEqual(entry['owed_by_user'], {'USD': Decimal('20')})
        self.assertEqual(entry['owed_to_user'], {})