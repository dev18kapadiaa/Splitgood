#!/usr/bin/env python3
file_path = r'C:\Users\admin\Downloads\Expense-Splitter\core\tests.py'

with open(file_path, 'r') as f:
    lines = f.readlines()

# Find the line with test_dashboard_shows_group_breakdown
for i, line in enumerate(lines):
    if 'def test_dashboard_shows_group_breakdown' in line:
        start_line = i
        break
else:
    print("Could not find test")
    exit(1)

# Find the next test method
end_line = None
for i in range(start_line + 1, len(lines)):
    if lines[i].strip().startswith('def test_'):
        end_line = i
        break

if end_line is None:
    end_line = len(lines)

# Replace the test
before_lines = lines[:start_line]
after_lines = lines[end_line:]

new_test = '''    def test_dashboard_shows_per_group_balances(self):
        """Verify dashboard shows one entry per user per group (not aggregated)."""
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
        
        # Should have 2 entries (one per group, not aggregated)
        self.assertEqual(len(balances), 2)
        
        group1_entry = next(b for b in balances if b['group'].id == group1.id)
        group2_entry = next(b for b in balances if b['group'].id == group2.id)
        
        # Group1: user1 owes user3 $43 (negative)
        self.assertEqual(group1_entry['balances']['USD'], Decimal('-43'))
        self.assertFalse(group1_entry['net_positive']) # user1 owes
        
        # Group2: user3 owes user1 $53 (positive)
        self.assertEqual(group2_entry['balances']['USD'], Decimal('53'))
        self.assertTrue(group2_entry['net_positive'])  # user1 is owed

'''

new_lines = before_lines + [new_test] + after_lines

with open(file_path, 'w') as f:
    f.writelines(new_lines)

print("Test updated successfully")
