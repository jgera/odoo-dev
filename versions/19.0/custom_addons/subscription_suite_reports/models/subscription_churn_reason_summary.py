from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionChurnReasonSummary(models.Model):
    _name = 'subscription.churn.reason.summary'
    _description = 'Subscription Churn Reason Summary'
    _order = 'closing_date desc, opening_date desc, company_id, currency_id, subscription_plan_id, reason_bucket, cancellation_reason_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    cancellation_reason_id = fields.Many2one('subscription.cancel.reason', string='Cancellation Reason', readonly=True, index=True)
    reason_bucket = fields.Selection(
        [
            ('specific', 'Specific Reason'),
            ('missing', 'Missing Reason'),
            ('all_reasons', 'All Reasons'),
        ],
        string='Reason Bucket',
        required=True,
        readonly=True,
        index=True,
    )
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection(
        [
            ('ready', 'Ready'),
            ('missing_reason', 'Missing Reason'),
            ('no_churn', 'No Churn'),
        ],
        string='Status',
        required=True,
        readonly=True,
        index=True,
    )

    churned_subscription_count = fields.Integer(string='Churned Subscriptions', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    average_churned_mrr = fields.Monetary(string='Average Churned MRR', currency_field='currency_id', readonly=True)
    feedback_count = fields.Integer(string='Feedback Count', readonly=True)
    feedback_coverage = fields.Float(string='Feedback Coverage (%)', readonly=True)

    _churn_reason_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one churn reason summary can exist for the same period and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_period_dates(self):
        for summary in self:
            if summary.opening_date > summary.closing_date:
                raise ValidationError(_("Closing date must be on or after opening date."))

    @api.model
    def _check_churn_reason_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate churn reason summaries."))

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id, reason_bucket, reason_id):
        plan_key = plan_id or 'all_plans'
        reason_key = reason_id or reason_bucket
        return '%s:%s:%s:%s:%s' % (company_id, currency_id, plan_key, reason_bucket, reason_key)

    @api.model
    def _prepare_subscription_domain(self, opening_date, closing_date, company=None, plan=None, reason=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_plan_id', '!=', False),
            ('subscription_state', 'in', ['cancelled', 'expired']),
            ('cancellation_date', '>=', opening_date),
            ('cancellation_date', '<=', closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        if reason:
            domain.append(('cancellation_reason_id', '=', reason.id))
        return domain

    @api.model
    def _prepare_existing_domain(self, opening_date, closing_date, company=None, plan=None, reason=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        if reason:
            domain.append(('cancellation_reason_id', '=', reason.id))
            domain.append(('reason_bucket', '=', 'specific'))
        return domain

    @api.model
    def _churn_mrr_by_subscription(self, subscriptions, opening_date, closing_date):
        movements = self.env['subscription.mrr.movement'].search([
            ('subscription_id', 'in', subscriptions.ids),
            ('movement_type', '=', 'churn'),
            ('movement_date', '>=', opening_date),
            ('movement_date', '<=', closing_date),
        ])
        amounts = defaultdict(float)
        for movement in movements:
            amounts[movement.subscription_id.id] += abs(movement.amount or 0.0)
        return amounts

    @api.model
    def _blank_bucket(self):
        return {
            'subscription_ids': set(),
            'churned_mrr': 0.0,
            'feedback_count': 0,
        }

    @api.model
    def _add_subscription_to_bucket(self, buckets, key, subscription, churn_mrr):
        bucket = buckets[key]
        bucket['subscription_ids'].add(subscription.id)
        bucket['churned_mrr'] += churn_mrr
        if subscription.cancellation_feedback:
            bucket['feedback_count'] += 1

    @api.model
    def _summary_values(self, opening_date, closing_date, company=None, plan=None, reason=None):
        subscriptions = self.env['sale.order'].search(
            self._prepare_subscription_domain(opening_date, closing_date, company=company, plan=plan, reason=reason)
        )
        if not subscriptions:
            return []
        churn_mrr_by_subscription = self._churn_mrr_by_subscription(subscriptions, opening_date, closing_date)
        buckets = defaultdict(self._blank_bucket)
        for subscription in subscriptions:
            reason_id = subscription.cancellation_reason_id.id or False
            reason_bucket = 'specific' if reason_id else 'missing'
            churn_mrr = churn_mrr_by_subscription.get(subscription.id, subscription.mrr or 0.0)
            plan_key = (
                subscription.company_id.id,
                subscription.currency_id.id,
                subscription.subscription_plan_id.id,
                reason_bucket,
                reason_id,
            )
            self._add_subscription_to_bucket(buckets, plan_key, subscription, churn_mrr)

            if not reason:
                all_reason_key = (
                    subscription.company_id.id,
                    subscription.currency_id.id,
                    subscription.subscription_plan_id.id,
                    'all_reasons',
                    False,
                )
                self._add_subscription_to_bucket(buckets, all_reason_key, subscription, churn_mrr)

            if not plan:
                all_plan_key = (
                    subscription.company_id.id,
                    subscription.currency_id.id,
                    False,
                    reason_bucket,
                    reason_id,
                )
                self._add_subscription_to_bucket(buckets, all_plan_key, subscription, churn_mrr)
                if not reason:
                    all_plan_all_reason_key = (
                        subscription.company_id.id,
                        subscription.currency_id.id,
                        False,
                        'all_reasons',
                        False,
                    )
                    self._add_subscription_to_bucket(buckets, all_plan_all_reason_key, subscription, churn_mrr)

        values = []
        generated_at = fields.Datetime.now()
        for (company_id, currency_id, plan_id, reason_bucket, reason_id), bucket in sorted(buckets.items()):
            churn_count = len(bucket['subscription_ids'])
            churned_mrr = bucket['churned_mrr']
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'cancellation_reason_id': reason_id,
                'reason_bucket': reason_bucket,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id, reason_bucket, reason_id),
                'generated_at': generated_at,
                'status': 'missing_reason' if reason_bucket == 'missing' else 'ready',
                'churned_subscription_count': churn_count,
                'churned_mrr': churned_mrr,
                'average_churned_mrr': churned_mrr / churn_count if churn_count else 0.0,
                'feedback_count': bucket['feedback_count'],
                'feedback_coverage': (bucket['feedback_count'] / churn_count) * 100.0 if churn_count else 0.0,
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None, reason=None):
        self._check_churn_reason_manager_access()
        opening_date = fields.Date.to_date(opening_date)
        closing_date = fields.Date.to_date(closing_date)
        if opening_date > closing_date:
            raise ValidationError(_("Closing date must be on or after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        if isinstance(reason, int):
            reason = self.env['subscription.cancel.reason'].browse(reason)
        self.search(self._prepare_existing_domain(opening_date, closing_date, company=company, plan=plan, reason=reason)).unlink()
        values = self._summary_values(opening_date, closing_date, company=company, plan=plan, reason=reason)
        return self.create(values) if values else self.browse()

    def _base_subscription_domain(self):
        self.ensure_one()
        domain = [
            ('is_subscription', '=', True),
            ('subscription_plan_id', '!=', False),
            ('subscription_state', 'in', ['cancelled', 'expired']),
            ('cancellation_date', '>=', self.opening_date),
            ('cancellation_date', '<=', self.closing_date),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        if self.reason_bucket == 'specific':
            domain.append(('cancellation_reason_id', '=', self.cancellation_reason_id.id))
        elif self.reason_bucket == 'missing':
            domain.append(('cancellation_reason_id', '=', False))
        return domain

    def action_view_source_subscriptions(self):
        self.ensure_one()
        return {
            'name': _('Churned Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._base_subscription_domain(),
        }

    def action_view_cancellation_requests(self):
        self.ensure_one()
        subscription_domain = self._base_subscription_domain()
        subscriptions = self.env['sale.order'].search(subscription_domain)
        domain = [('subscription_id', 'in', subscriptions.ids)]
        if self.reason_bucket == 'specific':
            domain.append(('reason_id', '=', self.cancellation_reason_id.id))
        elif self.reason_bucket == 'missing':
            domain.append(('reason_id', '=', False))
        return {
            'name': _('Cancellation Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.cancellation.request',
            'view_mode': 'list,form',
            'domain': domain,
        }
