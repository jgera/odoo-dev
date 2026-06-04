from odoo.tests.common import TransactionCase
from odoo import fields

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
