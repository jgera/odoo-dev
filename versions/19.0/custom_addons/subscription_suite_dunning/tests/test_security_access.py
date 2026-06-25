from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSubscriptionDunningSecurityAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.other_company = self.env['res.company'].create({'name': 'Dunning Security Company'})
        self.subscription_user = self._create_user(
            'dunning-security-user@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_user')],
            [self.company],
        )
        self.subscription_manager = self._create_user(
            'dunning-security-manager@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_manager')],
            [self.company, self.other_company],
        )

    def _create_user(self, login, groups, companies):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login,
            'login': login,
            'email': login,
            'company_id': companies[0].id,
            'company_ids': [Command.set([company.id for company in companies])],
            'group_ids': [Command.set([group.id for group in groups])],
        })

    def test_dunning_policies_are_company_scoped_for_subscription_users(self):
        own_policy = self.env['subscription.dunning.policy'].sudo().create({
            'name': 'Dunning Security Own',
            'company_id': self.company.id,
        })
        other_policy = self.env['subscription.dunning.policy'].sudo().create({
            'name': 'Dunning Security Other',
            'company_id': self.other_company.id,
        })

        visible = self.env['subscription.dunning.policy'].with_user(self.subscription_user).search([])
        manager_visible = self.env['subscription.dunning.policy'].with_user(self.subscription_manager).search([])

        self.assertIn(own_policy, visible)
        self.assertNotIn(other_policy, visible)
        self.assertIn(own_policy, manager_visible)
        self.assertIn(other_policy, manager_visible)

    def test_subscription_user_cannot_mutate_dunning_policy_but_manager_can(self):
        policy = self.env['subscription.dunning.policy'].create({'name': 'Dunning Security Mutation'})

        with self.assertRaises(AccessError):
            policy.with_user(self.subscription_user).write({'name': 'Blocked Dunning Mutation'})

        policy.with_user(self.subscription_manager).write({'name': 'Manager Dunning Mutation'})
        self.assertEqual(policy.name, 'Manager Dunning Mutation')
