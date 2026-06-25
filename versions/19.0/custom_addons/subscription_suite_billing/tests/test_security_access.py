from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSubscriptionBillingSecurityAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.other_company = self.env['res.company'].create({'name': 'Billing Security Company'})
        self.partner = self.env['res.partner'].create({'name': 'Billing Security Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Billing Security Product',
            'type': 'service',
            'list_price': 100.0,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Billing Security Plan',
            'code': 'BILLING-SECURITY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.subscription_user = self._create_user(
            'billing-security-user@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_user')],
            [self.company],
        )
        self.subscription_manager = self._create_user(
            'billing-security-manager@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_manager')],
            [self.company, self.other_company],
        )
        self.accounting_readonly = self._create_user(
            'billing-security-accounting@example.com',
            [self.env.ref('base.group_user'), self.env.ref('account.group_account_readonly')],
            [self.company],
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

    def _create_subscription_invoice_and_schedule(self):
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.name,
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })],
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'invoice_date': date(2026, 1, 1),
            'subscription_period_start': date(2026, 1, 1),
            'subscription_period_end': date(2026, 2, 1),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.name,
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        return self.env['subscription.deferred.revenue'].sudo().create({
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'service_period_start': date(2026, 1, 1),
            'service_period_end': date(2026, 2, 1),
            'recognition_method': 'straight_line_daily',
            'amount_total': 100.0,
            'state': 'ready',
        })

    def test_billing_records_are_company_scoped_for_subscription_users(self):
        own_run = self.env['subscription.billing.run'].sudo().create({
            'name': 'BILLING-SEC-OWN',
            'company_id': self.company.id,
        })
        other_run = self.env['subscription.billing.run'].sudo().create({
            'name': 'BILLING-SEC-OTHER',
            'company_id': self.other_company.id,
        })

        visible = self.env['subscription.billing.run'].with_user(self.subscription_user).search([])
        manager_visible = self.env['subscription.billing.run'].with_user(self.subscription_manager).search([])

        self.assertIn(own_run, visible)
        self.assertNotIn(other_run, visible)
        self.assertIn(own_run, manager_visible)
        self.assertIn(other_run, manager_visible)

    def test_accounting_readonly_can_inspect_finance_records_without_mutation(self):
        schedule = self._create_subscription_invoice_and_schedule()
        readonly_schedule = schedule.with_user(self.accounting_readonly)

        self.assertEqual(readonly_schedule.name, schedule.name)
        with self.assertRaises(AccessError):
            readonly_schedule.write({'state': 'cancelled'})
        with self.assertRaises(AccessError):
            self.env['subscription.deferred.revenue'].with_user(self.accounting_readonly).create({})

    def test_subscription_user_cannot_generate_or_mutate_finance_records(self):
        schedule = self._create_subscription_invoice_and_schedule()

        with self.assertRaises(AccessError):
            schedule.with_user(self.subscription_user).write({'state': 'cancelled'})
        with self.assertRaises(AccessError):
            self.env['subscription.deferred.revenue.post.wizard'].with_user(self.subscription_user).create({
                'cutoff_date': date(2026, 2, 1),
            })
