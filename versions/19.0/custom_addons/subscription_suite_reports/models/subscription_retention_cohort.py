from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionRetentionCohort(models.Model):
    _name = 'subscription.retention.cohort'
    _description = 'Subscription Retention Cohort'
    _order = 'period_month desc, cohort_month desc, company_id, currency_id, subscription_plan_id'

    cohort_month = fields.Date(string='Cohort Month', required=True, readonly=True, index=True)
    period_month = fields.Date(string='Period Month', required=True, readonly=True, index=True)
    cohort_age_months = fields.Integer(string='Cohort Age Months', readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([
        ('ready', 'Ready'),
    ], string='Status', required=True, readonly=True, index=True)

    starting_subscription_count = fields.Integer(string='Starting Subscriptions', readonly=True)
    retained_subscription_count = fields.Integer(string='Retained Subscriptions', readonly=True)
    churned_subscription_count = fields.Integer(string='Churned Subscriptions', readonly=True)
    starting_mrr = fields.Monetary(string='Starting MRR', currency_field='currency_id', readonly=True)
    retained_mrr = fields.Monetary(string='Retained MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    retention_rate = fields.Float(string='Retention Rate (%)', readonly=True)
    churn_rate = fields.Float(string='Churn Rate (%)', readonly=True)

    _retention_cohort_bucket_unique = models.Constraint(
        'UNIQUE(cohort_month, period_month, bucket_key)',
        'Only one retention cohort row can exist for the same cohort, period, and bucket.',
    )

    @api.constrains('cohort_month', 'period_month')
    def _check_month_range(self):
        for cohort in self:
            if cohort.period_month < cohort.cohort_month:
                raise ValidationError(_("Period month must be on or after cohort month."))

    @api.model
    def _check_cohort_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate retention cohorts."))

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
    def _month_age(self, cohort_month, period_month):
        return (
            (period_month.year - cohort_month.year) * 12
            + period_month.month
            - cohort_month.month
        )

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id, cohort_month, period_month):
        plan_key = plan_id or 'all_plans'
        return '%s:%s:%s:%s:%s' % (company_id, currency_id, plan_key, cohort_month, period_month)

    @api.model
    def _prepare_generation_domain(self, cohort_start_month, cohort_end_month, company=None, plan=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_plan_id', '!=', False),
            '|',
            ('subscription_start_date', '!=', False),
            ('trial_start_date', '!=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _subscription_cohort_month(self, subscription):
        start_date = subscription.subscription_start_date or subscription.trial_start_date
        return self._month_start(start_date) if start_date else False

    @api.model
    def _subscription_is_churned_for_period(self, subscription, period_month, generation_end_month):
        period_end = self._month_end(period_month)
        if subscription.cancellation_date and subscription.cancellation_date <= period_end:
            return True
        if (
            subscription.subscription_state in ('cancelled', 'expired')
            and not subscription.cancellation_date
            and period_month == generation_end_month
        ):
            return True
        return False

    @api.model
    def _prepare_existing_domain(self, cohort_start_month, cohort_end_month, company=None, plan=None):
        domain = [
            ('cohort_month', '>=', cohort_start_month),
            ('cohort_month', '<=', cohort_end_month),
            ('period_month', '>=', cohort_start_month),
            ('period_month', '<=', cohort_end_month),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _source_subscription_domain(self, cohort_month, company, currency, plan=None):
        cohort_end = self._month_end(cohort_month)
        domain = [
            ('is_subscription', '=', True),
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
            ('subscription_plan_id', '!=', False),
            '|',
            '&',
            ('subscription_start_date', '>=', cohort_month),
            ('subscription_start_date', '<=', cohort_end),
            '&',
            ('subscription_start_date', '=', False),
            '&',
            ('trial_start_date', '>=', cohort_month),
            ('trial_start_date', '<=', cohort_end),
        ]
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _cohort_values(self, cohort_start_month, cohort_end_month, company=None, plan=None):
        generation_end_month = self._month_start(cohort_end_month)
        cohort_start_month = self._month_start(cohort_start_month)
        cohort_end_month = self._month_start(cohort_end_month)
        subscriptions_by_bucket = defaultdict(list)
        subscriptions = self.env['sale.order'].search(
            self._prepare_generation_domain(cohort_start_month, cohort_end_month, company=company, plan=plan)
        )
        for subscription in subscriptions:
            cohort_month = self._subscription_cohort_month(subscription)
            if not cohort_month or cohort_month < cohort_start_month or cohort_month > cohort_end_month:
                continue
            plan_bucket = (
                subscription.company_id.id,
                subscription.currency_id.id,
                subscription.subscription_plan_id.id,
                cohort_month,
            )
            subscriptions_by_bucket[plan_bucket].append(subscription)
            if not plan:
                all_plan_bucket = (
                    subscription.company_id.id,
                    subscription.currency_id.id,
                    False,
                    cohort_month,
                )
                subscriptions_by_bucket[all_plan_bucket].append(subscription)

        values = []
        generated_at = fields.Datetime.now()
        for (company_id, currency_id, plan_id, cohort_month), bucket_subscriptions in sorted(subscriptions_by_bucket.items()):
            starting_count = len(bucket_subscriptions)
            starting_mrr = sum(subscription.mrr or 0.0 for subscription in bucket_subscriptions)
            for period_month in self._month_range(cohort_month, cohort_end_month):
                retained = []
                churned = []
                for subscription in bucket_subscriptions:
                    if self._subscription_is_churned_for_period(subscription, period_month, generation_end_month):
                        churned.append(subscription)
                    else:
                        retained.append(subscription)
                retained_count = len(retained)
                churned_count = len(churned)
                retained_mrr = sum(subscription.mrr or 0.0 for subscription in retained)
                churned_mrr = sum(subscription.mrr or 0.0 for subscription in churned)
                values.append({
                    'cohort_month': cohort_month,
                    'period_month': period_month,
                    'cohort_age_months': self._month_age(cohort_month, period_month),
                    'company_id': company_id,
                    'currency_id': currency_id,
                    'subscription_plan_id': plan_id,
                    'bucket_key': self._bucket_key(company_id, currency_id, plan_id, cohort_month, period_month),
                    'generated_at': generated_at,
                    'status': 'ready',
                    'starting_subscription_count': starting_count,
                    'retained_subscription_count': retained_count,
                    'churned_subscription_count': churned_count,
                    'starting_mrr': starting_mrr,
                    'retained_mrr': retained_mrr,
                    'churned_mrr': churned_mrr,
                    'retention_rate': (retained_count / starting_count) * 100.0 if starting_count else 0.0,
                    'churn_rate': (churned_count / starting_count) * 100.0 if starting_count else 0.0,
                })
        return values

    @api.model
    def generate_for_period(self, cohort_start_month, cohort_end_month, company=None, plan=None):
        self._check_cohort_manager_access()
        cohort_start_month = self._month_start(cohort_start_month)
        cohort_end_month = self._month_start(cohort_end_month)
        if cohort_start_month > cohort_end_month:
            raise ValidationError(_("Cohort end month must be on or after cohort start month."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(
            self._prepare_existing_domain(cohort_start_month, cohort_end_month, company=company, plan=plan)
        ).unlink()
        values = self._cohort_values(cohort_start_month, cohort_end_month, company=company, plan=plan)
        return self.create(values) if values else self.browse()

    def action_view_subscriptions(self):
        self.ensure_one()
        domain = self._source_subscription_domain(
            self.cohort_month,
            self.company_id,
            self.currency_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': _('Cohort Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': domain,
        }
