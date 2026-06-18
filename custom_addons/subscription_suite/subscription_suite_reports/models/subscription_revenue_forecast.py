from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionRevenueForecast(models.Model):
    _name = 'subscription.revenue.forecast'
    _description = 'Subscription Revenue Forecast'
    _order = 'forecast_month, company_id, currency_id, subscription_plan_id'

    forecast_month = fields.Date(string='Forecast Month', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([('ready', 'Ready')], string='Status', required=True, readonly=True, index=True)
    source_count = fields.Integer(string='Source Subscriptions', readonly=True)

    active_base_mrr = fields.Monetary(string='Active Base MRR', currency_field='currency_id', readonly=True)
    upcoming_invoice_count = fields.Integer(string='Upcoming Invoices', readonly=True)
    upcoming_invoice_mrr = fields.Monetary(string='Upcoming Invoice MRR', currency_field='currency_id', readonly=True)
    renewal_due_count = fields.Integer(string='Renewals Due', readonly=True)
    renewal_due_mrr = fields.Monetary(string='Renewal Due MRR', currency_field='currency_id', readonly=True)
    scheduled_churn_count = fields.Integer(string='Scheduled Churn', readonly=True)
    scheduled_churn_mrr = fields.Monetary(string='Scheduled Churn MRR', currency_field='currency_id', readonly=True)
    net_forecast_mrr = fields.Monetary(string='Net Forecast MRR', currency_field='currency_id', readonly=True)

    _revenue_forecast_bucket_unique = models.Constraint(
        'UNIQUE(forecast_month, bucket_key)',
        'Only one revenue forecast row can exist for the same month and bucket.',
    )

    @api.constrains('forecast_month')
    def _check_forecast_month(self):
        for forecast in self:
            if forecast.forecast_month != self._month_start(forecast.forecast_month):
                raise ValidationError(_("Forecast month must be the first day of a month."))

    @api.model
    def _check_forecast_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate revenue forecasts."))

    @api.model
    def _month_start(self, value):
        value = fields.Date.to_date(value)
        return value.replace(day=1)

    @api.model
    def _month_end(self, value):
        return self._month_start(value) + relativedelta(months=1, days=-1)

    @api.model
    def _month_range(self, start_month, end_month):
        current = self._month_start(start_month)
        end_month = self._month_start(end_month)
        while current <= end_month:
            yield current
            current += relativedelta(months=1)

    @api.model
    def _forecast_states(self):
        return ('active', 'trial', 'paused', 'past_due')

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id, forecast_month):
        return '%s:%s:%s:%s' % (company_id, currency_id, plan_id or 'all_plans', forecast_month)

    @api.model
    def _prepare_subscription_domain(self, start_month, end_month, company=None, plan=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_plan_id', '!=', False),
            ('subscription_state', 'not in', ['draft']),
            '|',
            '|',
            '|',
            ('subscription_state', 'in', list(self._forecast_states())),
            '&',
            ('next_invoice_date', '>=', start_month),
            ('next_invoice_date', '<=', self._month_end(end_month)),
            '&',
            ('subscription_end_date', '>=', start_month),
            ('subscription_end_date', '<=', self._month_end(end_month)),
            '&',
            ('pending_cancellation', '=', True),
            '&',
            ('cancellation_effective_date', '>=', start_month),
            ('cancellation_effective_date', '<=', self._month_end(end_month)),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _prepare_existing_domain(self, start_month, end_month, company=None, plan=None):
        domain = [('forecast_month', '>=', start_month), ('forecast_month', '<=', end_month)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _blank_bucket(self):
        return {
            'source_ids': set(),
            'active_base_mrr': 0.0,
            'upcoming_invoice_ids': set(),
            'upcoming_invoice_mrr': 0.0,
            'renewal_due_ids': set(),
            'renewal_due_mrr': 0.0,
            'scheduled_churn_ids': set(),
            'scheduled_churn_mrr': 0.0,
        }

    @api.model
    def _add_subscription_to_bucket(self, buckets, key, subscription, forecast_month):
        bucket = buckets[key]
        bucket['source_ids'].add(subscription.id)
        state = subscription.subscription_state
        mrr = subscription.mrr or 0.0
        if state in self._forecast_states():
            bucket['active_base_mrr'] += mrr
        if state in self._forecast_states() and subscription.next_invoice_date:
            next_invoice_month = self._month_start(subscription.next_invoice_date)
            if next_invoice_month == forecast_month:
                bucket['upcoming_invoice_ids'].add(subscription.id)
                bucket['upcoming_invoice_mrr'] += mrr
        if state not in ('cancelled', 'expired') and subscription.subscription_end_date:
            if self._month_start(subscription.subscription_end_date) == forecast_month:
                bucket['renewal_due_ids'].add(subscription.id)
                bucket['renewal_due_mrr'] += mrr
        if subscription.pending_cancellation and subscription.cancellation_effective_date:
            if self._month_start(subscription.cancellation_effective_date) == forecast_month:
                bucket['scheduled_churn_ids'].add(subscription.id)
                bucket['scheduled_churn_mrr'] += mrr

    @api.model
    def _forecast_values(self, start_month, end_month, company=None, plan=None):
        subscriptions = self.env['sale.order'].search(
            self._prepare_subscription_domain(start_month, end_month, company=company, plan=plan)
        )
        buckets = defaultdict(self._blank_bucket)
        for forecast_month in self._month_range(start_month, end_month):
            for subscription in subscriptions:
                plan_key = (
                    subscription.company_id.id,
                    subscription.currency_id.id,
                    subscription.subscription_plan_id.id,
                    forecast_month,
                )
                self._add_subscription_to_bucket(buckets, plan_key, subscription, forecast_month)
                if not plan:
                    all_plan_key = (
                        subscription.company_id.id,
                        subscription.currency_id.id,
                        False,
                        forecast_month,
                    )
                    self._add_subscription_to_bucket(buckets, all_plan_key, subscription, forecast_month)

        values = []
        generated_at = fields.Datetime.now()
        for (company_id, currency_id, plan_id, forecast_month), bucket in sorted(buckets.items()):
            has_signal = (
                bucket['source_ids']
                or bucket['upcoming_invoice_ids']
                or bucket['renewal_due_ids']
                or bucket['scheduled_churn_ids']
            )
            if not has_signal:
                continue
            values.append({
                'forecast_month': forecast_month,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id, forecast_month),
                'generated_at': generated_at,
                'status': 'ready',
                'source_count': len(bucket['source_ids']),
                'active_base_mrr': bucket['active_base_mrr'],
                'upcoming_invoice_count': len(bucket['upcoming_invoice_ids']),
                'upcoming_invoice_mrr': bucket['upcoming_invoice_mrr'],
                'renewal_due_count': len(bucket['renewal_due_ids']),
                'renewal_due_mrr': bucket['renewal_due_mrr'],
                'scheduled_churn_count': len(bucket['scheduled_churn_ids']),
                'scheduled_churn_mrr': bucket['scheduled_churn_mrr'],
                'net_forecast_mrr': (
                    bucket['active_base_mrr']
                    + bucket['upcoming_invoice_mrr']
                    - bucket['scheduled_churn_mrr']
                ),
            })
        return values

    @api.model
    def generate_for_period(self, forecast_start_month, forecast_end_month, company=None, plan=None):
        self._check_forecast_manager_access()
        forecast_start_month = self._month_start(forecast_start_month)
        forecast_end_month = self._month_start(forecast_end_month)
        if forecast_start_month > forecast_end_month:
            raise ValidationError(_("Forecast end month must be on or after forecast start month."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(
            self._prepare_existing_domain(forecast_start_month, forecast_end_month, company=company, plan=plan)
        ).unlink()
        values = self._forecast_values(forecast_start_month, forecast_end_month, company=company, plan=plan)
        return self.create(values) if values else self.browse()

    def _base_subscription_domain(self):
        self.ensure_one()
        domain = [
            ('is_subscription', '=', True),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('subscription_plan_id', '!=', False),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def _source_subscription_domain(self):
        self.ensure_one()
        month_end = self._month_end(self.forecast_month)
        return self._base_subscription_domain() + [
            '|',
            '|',
            '|',
            ('subscription_state', 'in', list(self._forecast_states())),
            '&',
            '&',
            ('subscription_state', 'in', list(self._forecast_states())),
            ('next_invoice_date', '>=', self.forecast_month),
            ('next_invoice_date', '<=', month_end),
            '&',
            '&',
            ('subscription_state', 'not in', ['cancelled', 'expired']),
            ('subscription_end_date', '>=', self.forecast_month),
            ('subscription_end_date', '<=', month_end),
            '&',
            '&',
            ('pending_cancellation', '=', True),
            ('cancellation_effective_date', '>=', self.forecast_month),
            ('cancellation_effective_date', '<=', month_end),
        ]

    def action_view_source_subscriptions(self):
        self.ensure_one()
        return {
            'name': _('Forecast Source Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._source_subscription_domain(),
        }

    def action_view_upcoming_invoices(self):
        self.ensure_one()
        domain = self._base_subscription_domain() + [
            ('subscription_state', 'in', list(self._forecast_states())),
            ('next_invoice_date', '>=', self.forecast_month),
            ('next_invoice_date', '<=', self._month_end(self.forecast_month)),
        ]
        return {
            'name': _('Upcoming Subscription Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_view_renewals_due(self):
        self.ensure_one()
        domain = self._base_subscription_domain() + [
            ('subscription_state', 'not in', ['cancelled', 'expired']),
            ('subscription_end_date', '>=', self.forecast_month),
            ('subscription_end_date', '<=', self._month_end(self.forecast_month)),
        ]
        return {
            'name': _('Renewals Due'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_view_scheduled_churn(self):
        self.ensure_one()
        domain = self._base_subscription_domain() + [
            ('pending_cancellation', '=', True),
            ('cancellation_effective_date', '>=', self.forecast_month),
            ('cancellation_effective_date', '<=', self._month_end(self.forecast_month)),
        ]
        return {
            'name': _('Scheduled Churn'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': domain,
        }
