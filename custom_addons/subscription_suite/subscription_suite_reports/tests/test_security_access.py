from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSubscriptionReportsSecurityAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.other_company = self.env['res.company'].create({'name': 'Reports Security Company'})
        self.currency = self.company.currency_id
        self.plan = self.env['subscription.plan'].create({
            'name': 'Reports Security Plan',
            'code': 'REPORTS-SECURITY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'company_id': self.company.id,
        })
        self.other_plan = self.env['subscription.plan'].sudo().create({
            'name': 'Reports Security Other Plan',
            'code': 'REPORTS-SECURITY-OTHER',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'company_id': self.other_company.id,
        })
        self.subscription_user = self._create_user(
            'reports-security-user@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_user')],
            [self.company],
        )
        self.subscription_manager = self._create_user(
            'reports-security-manager@example.com',
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

    def _create_snapshot(self, company, plan):
        return self.env['subscription.mrr.snapshot'].sudo().create({
            'snapshot_date': date(2026, 1, 1),
            'company_id': company.id,
            'currency_id': company.currency_id.id,
            'subscription_plan_id': plan.id,
            'subscription_count': 1,
            'total_recurring_mrr': 100.0,
            'arr': 1200.0,
        })

    def test_generated_report_rows_are_company_scoped_for_subscription_users(self):
        own_snapshot = self._create_snapshot(self.company, self.plan)
        other_snapshot = self._create_snapshot(self.other_company, self.other_plan)

        visible = self.env['subscription.mrr.snapshot'].with_user(self.subscription_user).search([])
        manager_visible = self.env['subscription.mrr.snapshot'].with_user(self.subscription_manager).search([])

        self.assertIn(own_snapshot, visible)
        self.assertNotIn(other_snapshot, visible)
        self.assertIn(own_snapshot, manager_visible)
        self.assertIn(other_snapshot, manager_visible)

    def test_subscription_user_cannot_mutate_or_generate_report_rows(self):
        snapshot = self._create_snapshot(self.company, self.plan)

        with self.assertRaises(AccessError):
            snapshot.with_user(self.subscription_user).write({'subscription_count': 2})
        with self.assertRaises(AccessError):
            self.env['subscription.mrr.snapshot'].with_user(self.subscription_user).generate_for_date(
                date(2026, 1, 1),
                company=self.company,
            )
