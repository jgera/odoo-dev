from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionSecurityAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Security Customer'})
        self.other_partner = self.env['res.partner'].create({'name': 'Other Security Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Security Subscription Product',
            'type': 'service',
            'list_price': 100.0,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Security Monthly',
            'code': 'SEC-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.reason = self.env['subscription.cancel.reason'].create({'name': 'Security Cancellation'})
        self.subscription_user = self._create_user(
            'security-subscription-user@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_user')],
            self.partner,
        )
        self.other_subscription_user = self._create_user(
            'security-other-subscription-user@example.com',
            [self.env.ref('base.group_portal')],
            self.other_partner,
        )
        self.subscription_manager = self._create_user(
            'security-subscription-manager@example.com',
            [self.env.ref('base.group_user'), self.env.ref('subscription_suite.group_subscription_manager')],
            self.partner,
        )

    def _create_user(self, login, groups, partner):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login,
            'login': login,
            'email': login,
            'partner_id': partner.id,
            'company_id': self.env.company.id,
            'company_ids': [Command.set([self.env.company.id])],
            'group_ids': [Command.set([group.id for group in groups])],
        })

    def _create_subscription(self, partner, user=False, state='active'):
        return self.env['sale.order'].create({
            'partner_id': partner.id,
            'user_id': user.id if user else False,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': self.plan.id,
            'subscription_start_date': fields.Date.today(),
            'next_invoice_date': fields.Date.today(),
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.name,
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })],
        })

    def test_subscription_user_record_rule_hides_other_salesperson_subscription(self):
        own_subscription = self._create_subscription(self.partner, user=self.subscription_user)
        unassigned_subscription = self._create_subscription(self.partner)
        other_subscription = self._create_subscription(self.other_partner, user=self.other_subscription_user)

        visible = self.env['sale.order'].with_user(self.subscription_user).search([
            ('is_subscription', '=', True),
        ])
        manager_visible = self.env['sale.order'].with_user(self.subscription_manager).search([
            ('is_subscription', '=', True),
        ])

        self.assertIn(own_subscription, visible)
        self.assertIn(unassigned_subscription, visible)
        self.assertNotIn(other_subscription, visible)
        self.assertIn(other_subscription, manager_visible)

    def test_subscription_user_cannot_mutate_plan_but_manager_can(self):
        with self.assertRaises(AccessError):
            self.plan.with_user(self.subscription_user).write({'name': 'Blocked Security Plan'})

        self.plan.with_user(self.subscription_manager).write({'name': 'Manager Security Plan'})
        self.assertEqual(self.plan.name, 'Manager Security Plan')

    def test_portal_lifecycle_and_cancellation_helpers_reject_other_customer_requester(self):
        active_subscription = self._create_subscription(self.partner, state='active')
        cancellation_subscription = self._create_subscription(self.partner, state='active')

        with self.assertRaises(ValidationError):
            active_subscription.sudo()._portal_request_lifecycle_action(
                'pause',
                'Other customer trying to pause',
                self.other_subscription_user,
            )
        with self.assertRaises(ValidationError):
            cancellation_subscription.sudo()._portal_request_cancellation(
                self.reason,
                'Other customer trying to cancel',
                self.other_subscription_user,
            )
