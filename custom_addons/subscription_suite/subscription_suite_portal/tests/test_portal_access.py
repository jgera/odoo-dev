from odoo import fields
from odoo.tests.common import TransactionCase

class TestPortalAccess(TransactionCase):

    def setUp(self):
        super(TestPortalAccess, self).setUp()
        self.partner = self.env['res.partner'].create({'name': 'Portal Customer'})
        self.plan = self.env['subscription.plan'].create({
            'name': 'Portal Test Plan',
            'code': 'PORTAL-TEST',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.upgrade_plan = self.env['subscription.plan'].create({
            'name': 'Portal Upgrade Plan',
            'code': 'PORTAL-UPGRADE',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
        })

    def test_01_subscription_is_visible(self):
        """Test that a subscription is found when searching for is_subscription."""
        subs = self.env['sale.order'].search([
            ('partner_id', '=', self.partner.id),
            ('is_subscription', '=', True),
        ])
        self.assertIn(self.sub, subs)

    def test_02_non_subscription_not_included(self):
        """Test that regular sale orders are not returned in subscription searches."""
        regular_so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': False,
        })
        subs = self.env['sale.order'].search([
            ('partner_id', '=', self.partner.id),
            ('is_subscription', '=', True),
        ])
        self.assertNotIn(regular_so, subs)

    def test_03_portal_plan_change_status_data_exists(self):
        """Portal detail values can include pending plan changes and approval requests."""
        today = fields.Date.today()
        self.sub.write({
            'pending_plan_change_id': self.upgrade_plan.id,
            'pending_plan_change_date': today,
            'pending_plan_change_type': 'upgrade',
        })
        request = self.env['subscription.plan.change.request'].create({
            'subscription_id': self.sub.id,
            'current_plan_id': self.plan.id,
            'requested_plan_id': self.upgrade_plan.id,
            'requested_effective_date': today,
            'requested_timing': 'next_period',
            'change_type': 'upgrade',
            'old_mrr': 0.0,
            'new_mrr': 0.0,
        })

        portal_requests = self.env['subscription.plan.change.request'].search([
            ('subscription_id', '=', self.sub.id),
        ])

        self.assertEqual(self.sub.pending_plan_change_id, self.upgrade_plan)
        self.assertIn(request, portal_requests)

    def test_04_portal_cancellation_request_status_data_exists(self):
        """Portal detail values can include scheduled cancellation and request status."""
        today = fields.Date.today()
        reason = self.env['subscription.cancel.reason'].create({'name': 'Portal cancellation reason'})
        self.sub.write({
            'pending_cancellation': True,
            'cancellation_requested_date': today,
            'cancellation_effective_date': today,
            'cancellation_policy_applied': 'end_of_period',
            'cancellation_reason_id': reason.id,
        })
        request = self.env['subscription.cancellation.request'].create({
            'subscription_id': self.sub.id,
            'reason_id': reason.id,
            'feedback': 'Portal cancellation request',
            'requested_effective_date': today,
            'requested_policy': 'end_of_period',
        })

        portal_requests = self.env['subscription.cancellation.request'].search([
            ('subscription_id', '=', self.sub.id),
        ])

        self.assertTrue(self.sub.pending_cancellation)
        self.assertEqual(self.sub.cancellation_reason_id, reason)
        self.assertIn(request, portal_requests)

    def test_05_portal_lifecycle_request_status_data_exists(self):
        """Portal detail values can include pause/resume request status."""
        request = self.env['subscription.lifecycle.request'].create({
            'subscription_id': self.sub.id,
            'request_type': 'pause',
            'feedback': 'Portal pause request',
        })

        portal_requests = self.env['subscription.lifecycle.request'].search([
            ('subscription_id', '=', self.sub.id),
        ])

        self.assertIn(request, portal_requests)
        self.assertEqual(request.state, 'pending')
        self.assertEqual(request.request_type, 'pause')
