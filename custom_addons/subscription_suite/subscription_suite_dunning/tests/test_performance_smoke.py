from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionDunningPerformanceSmoke(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Dunning Performance Customer'})
        self.policy = self.env['subscription.dunning.policy'].create({
            'name': 'Dunning Performance Policy',
            'grace_period_days': 0,
            'final_action': 'pause',
            'final_action_delay': 5,
        })
        self.template = self.env['mail.template'].create({
            'name': 'Dunning Performance Template',
            'model_id': self.env.ref('sale.model_sale_order').id,
            'subject': 'Dunning performance {{ object.name }}',
            'email_from': '{{ object.company_id.email or "billing@example.com" }}',
            'email_to': '{{ object.partner_id.email or "customer@example.com" }}',
            'body_html': '<p>Recover now</p>',
        })
        self.step = self.env['subscription.dunning.policy.line'].create({
            'policy_id': self.policy.id,
            'delay_days': 1,
            'action_type': 'email',
            'email_template_id': self.template.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Dunning Performance Monthly',
            'code': 'PERF-DUNNING-MONTHLY',
            'dunning_policy_id': self.policy.id,
        })

    def _create_subscription(self, index, state='past_due', due=True):
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': self.plan.id,
            'dunning_start_date': fields.Date.today() - timedelta(days=2),
            'next_dunning_date': fields.Date.today() if due else fields.Date.today() + timedelta(days=3),
        })
        return subscription

    def test_dunning_cron_medium_smoke_is_scoped_and_idempotent(self):
        due_subscriptions = self.env['sale.order']
        for index in range(10):
            due_subscriptions |= self._create_subscription(index)
        future_subscription = self._create_subscription('future', due=False)
        active_subscription = self._create_subscription('active', state='active')

        self.env['sale.order']._cron_process_dunning()
        first_attempts = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', 'in', due_subscriptions.ids),
        ])

        self.assertEqual(len(first_attempts), len(due_subscriptions))
        self.assertEqual(set(first_attempts.mapped('state')), {'done'})
        operation_run = self.env['subscription.operation.run'].search([
            ('operation_type', '=', 'dunning'),
        ], order='id desc', limit=1)
        self.assertEqual(operation_run.state, 'success')
        self.assertEqual(operation_run.processed_count, len(due_subscriptions))
        self.assertEqual(operation_run.dunning_attempt_ids, first_attempts)
        self.assertFalse(self.env['subscription.dunning.attempt'].search([
            ('subscription_id', 'in', (future_subscription | active_subscription).ids),
        ]))

        self.env['sale.order']._cron_process_dunning()
        second_attempts = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', 'in', due_subscriptions.ids),
        ])

        self.assertEqual(second_attempts, first_attempts)
        self.assertTrue(all(subscription.next_dunning_date > fields.Date.today() for subscription in due_subscriptions))

    def test_dunning_cron_respects_batch_size(self):
        self.env['ir.config_parameter'].sudo().set_param('subscription_suite.dunning_batch_size', 4)
        due_subscriptions = self.env['sale.order']
        for index in range(9):
            due_subscriptions |= self._create_subscription('batch-%s' % index)

        self.env['sale.order']._cron_process_dunning()
        first_attempts = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', 'in', due_subscriptions.ids),
        ])

        self.assertEqual(len(first_attempts), 4)

        self.env['sale.order']._cron_process_dunning()
        second_attempts = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', 'in', due_subscriptions.ids),
        ])

        self.assertEqual(len(second_attempts), 8)
