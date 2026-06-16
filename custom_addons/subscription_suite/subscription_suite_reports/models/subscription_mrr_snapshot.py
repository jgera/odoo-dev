from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class SubscriptionMrrSnapshot(models.Model):
    _name = 'subscription.mrr.snapshot'
    _description = 'Subscription MRR Snapshot'
    _order = 'snapshot_date desc, company_id, currency_id, subscription_plan_id'

    snapshot_date = fields.Date(
        string='Snapshot Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        index=True,
        readonly=True,
    )
    subscription_plan_id = fields.Many2one(
        'subscription.plan',
        string='Subscription Plan',
        required=True,
        index=True,
        readonly=True,
    )
    generated_at = fields.Datetime(string='Generated At', readonly=True)

    subscription_count = fields.Integer(string='Subscriptions', readonly=True)
    trial_count = fields.Integer(string='Trial Subscriptions', readonly=True)
    active_count = fields.Integer(string='Active Subscriptions', readonly=True)
    paused_count = fields.Integer(string='Paused Subscriptions', readonly=True)
    past_due_count = fields.Integer(string='Past Due Subscriptions', readonly=True)
    cancelled_count = fields.Integer(string='Cancelled Subscriptions', readonly=True)
    expired_count = fields.Integer(string='Expired Subscriptions', readonly=True)
    churned_count = fields.Integer(string='Churned Subscriptions', readonly=True)

    trial_mrr = fields.Monetary(string='Trial MRR', currency_field='currency_id', readonly=True)
    active_mrr = fields.Monetary(string='Active MRR', currency_field='currency_id', readonly=True)
    paused_mrr = fields.Monetary(string='Paused MRR', currency_field='currency_id', readonly=True)
    past_due_mrr = fields.Monetary(string='Past Due MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    total_recurring_mrr = fields.Monetary(string='Total Recurring MRR', currency_field='currency_id', readonly=True)
    arr = fields.Monetary(string='ARR', currency_field='currency_id', readonly=True)

    _snapshot_bucket_unique = models.Constraint(
        'UNIQUE(snapshot_date, company_id, currency_id, subscription_plan_id)',
        'Only one MRR snapshot can exist for the same date, company, currency, and plan.',
    )

    @api.model
    def _check_snapshot_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate MRR snapshots."))

    @api.model
    def _get_snapshot_states(self):
        return ('trial', 'active', 'paused', 'past_due', 'cancelled', 'expired')

    @api.model
    def _get_recurring_mrr_states(self):
        return ('trial', 'active', 'paused', 'past_due')

    @api.model
    def _get_churned_states(self):
        return ('cancelled', 'expired')

    @api.model
    def _prepare_snapshot_domain(self, snapshot_date, company=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_plan_id', '!=', False),
            ('subscription_state', 'in', list(self._get_snapshot_states())),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        return domain

    @api.model
    def _get_snapshot_bucket_values(self, snapshot_date, company=None):
        buckets = defaultdict(lambda: {
            'subscription_count': 0,
            'trial_count': 0,
            'active_count': 0,
            'paused_count': 0,
            'past_due_count': 0,
            'cancelled_count': 0,
            'expired_count': 0,
            'churned_count': 0,
            'trial_mrr': 0.0,
            'active_mrr': 0.0,
            'paused_mrr': 0.0,
            'past_due_mrr': 0.0,
            'churned_mrr': 0.0,
            'total_recurring_mrr': 0.0,
        })
        recurring_states = self._get_recurring_mrr_states()
        churned_states = self._get_churned_states()
        subscriptions = self.env['sale.order'].search(self._prepare_snapshot_domain(snapshot_date, company=company))
        for subscription in subscriptions:
            key = (
                subscription.company_id.id,
                subscription.currency_id.id,
                subscription.subscription_plan_id.id,
            )
            bucket = buckets[key]
            state = subscription.subscription_state
            mrr = subscription.mrr or 0.0
            bucket['subscription_count'] += 1
            bucket['%s_count' % state] += 1
            if state in churned_states:
                bucket['churned_count'] += 1
                bucket['churned_mrr'] += mrr
            elif state in recurring_states:
                bucket['total_recurring_mrr'] += mrr
                bucket['%s_mrr' % state] += mrr
        values = []
        generated_at = fields.Datetime.now()
        for (company_id, currency_id, plan_id), bucket in buckets.items():
            total_recurring_mrr = bucket['total_recurring_mrr']
            values.append({
                'snapshot_date': snapshot_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'generated_at': generated_at,
                'subscription_count': bucket['subscription_count'],
                'trial_count': bucket['trial_count'],
                'active_count': bucket['active_count'],
                'paused_count': bucket['paused_count'],
                'past_due_count': bucket['past_due_count'],
                'cancelled_count': bucket['cancelled_count'],
                'expired_count': bucket['expired_count'],
                'churned_count': bucket['churned_count'],
                'trial_mrr': bucket['trial_mrr'],
                'active_mrr': bucket['active_mrr'],
                'paused_mrr': bucket['paused_mrr'],
                'past_due_mrr': bucket['past_due_mrr'],
                'churned_mrr': bucket['churned_mrr'],
                'total_recurring_mrr': total_recurring_mrr,
                'arr': total_recurring_mrr * 12,
            })
        return values

    @api.model
    def generate_for_date(self, snapshot_date=None, company=None):
        self._check_snapshot_manager_access()
        snapshot_date = snapshot_date or fields.Date.context_today(self)
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        existing_domain = [('snapshot_date', '=', snapshot_date)]
        if company:
            existing_domain.append(('company_id', '=', company.id))
        self.search(existing_domain).unlink()
        values = self._get_snapshot_bucket_values(snapshot_date, company=company)
        return self.create(values) if values else self.browse()

    @api.model
    def _cron_generate_daily_snapshot(self):
        return self.sudo().generate_for_date(fields.Date.context_today(self))

    @api.model
    def action_open_generate_wizard(self):
        self._check_snapshot_manager_access()
        return {
            'name': _('Generate MRR Snapshot'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.snapshot.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
