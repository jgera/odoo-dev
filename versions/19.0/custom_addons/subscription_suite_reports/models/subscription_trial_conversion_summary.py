from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionTrialConversionSummary(models.Model):
    _name = 'subscription.trial.conversion.summary'
    _description = 'Subscription Trial Conversion Summary'
    _order = 'closing_date desc, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([('ready', 'Ready')], string='Status', required=True, readonly=True, default='ready')

    trials_started_count = fields.Integer(string='Trials Started', readonly=True)
    trials_converted_count = fields.Integer(string='Trials Converted', readonly=True)
    trials_expired_count = fields.Integer(string='Trials Expired', readonly=True)
    active_trial_count = fields.Integer(string='Active Trials', readonly=True)
    converted_mrr = fields.Monetary(string='Converted MRR', currency_field='currency_id', readonly=True)
    active_trial_mrr = fields.Monetary(string='Active Trial MRR', currency_field='currency_id', readonly=True)
    conversion_rate = fields.Float(string='Conversion Rate (%)', readonly=True)
    expiry_rate = fields.Float(string='Expiry Rate (%)', readonly=True)
    average_trial_length_days = fields.Float(string='Average Trial Length (Days)', readonly=True)

    _trial_conversion_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one trial conversion summary can exist for the same period and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_period(self):
        for summary in self:
            if summary.opening_date and summary.closing_date and summary.opening_date > summary.closing_date:
                raise ValidationError(_("Opening date must be on or before closing date."))

    @api.model
    def _check_trial_conversion_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate trial conversion summaries."))

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id):
        return '%s:%s:%s' % (company_id, currency_id, plan_id or 'all_plans')

    @api.model
    def _prepare_existing_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _prepare_trial_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_quote_type', '=', False),
            ('subscription_plan_id', '!=', False),
            ('trial_start_date', '>=', opening_date),
            ('trial_start_date', '<=', closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _blank_bucket(self):
        return {
            'trial_ids': set(),
            'converted_ids': set(),
            'expired_ids': set(),
            'active_trial_ids': set(),
            'converted_mrr': 0.0,
            'active_trial_mrr': 0.0,
            'trial_days_total': 0.0,
            'trial_days_count': 0,
        }

    @api.model
    def _is_converted_trial(self, subscription):
        return bool(
            subscription.subscription_start_date
            and subscription.subscription_state not in ('trial', 'cancelled', 'expired')
        )

    @api.model
    def _is_expired_trial(self, subscription, closing_date):
        return bool(
            subscription.subscription_state == 'expired'
            and not subscription.subscription_start_date
            and subscription.trial_end_date
            and subscription.trial_end_date <= closing_date
        )

    @api.model
    def _trial_length_days(self, subscription, closing_date):
        if not subscription.trial_start_date:
            return 0.0
        end_date = subscription.subscription_start_date or subscription.trial_end_date or closing_date
        if end_date < subscription.trial_start_date:
            return 0.0
        return float((end_date - subscription.trial_start_date).days)

    @api.model
    def _add_subscription_to_bucket(self, buckets, key, subscription, closing_date):
        bucket = buckets[key]
        bucket['trial_ids'].add(subscription.id)
        bucket['trial_days_total'] += self._trial_length_days(subscription, closing_date)
        bucket['trial_days_count'] += 1
        if self._is_converted_trial(subscription):
            bucket['converted_ids'].add(subscription.id)
            bucket['converted_mrr'] += subscription.mrr or 0.0
        elif self._is_expired_trial(subscription, closing_date):
            bucket['expired_ids'].add(subscription.id)
        elif subscription.subscription_state == 'trial':
            bucket['active_trial_ids'].add(subscription.id)
            bucket['active_trial_mrr'] += subscription.mrr or 0.0

    @api.model
    def _summary_values(self, opening_date, closing_date, company=None, plan=None):
        subscriptions = self.env['sale.order'].search(
            self._prepare_trial_domain(opening_date, closing_date, company=company, plan=plan)
        )
        buckets = defaultdict(self._blank_bucket)
        for subscription in subscriptions:
            plan_key = (
                subscription.company_id.id,
                subscription.currency_id.id,
                subscription.subscription_plan_id.id,
            )
            self._add_subscription_to_bucket(buckets, plan_key, subscription, closing_date)
            if not plan:
                all_plan_key = (
                    subscription.company_id.id,
                    subscription.currency_id.id,
                    False,
                )
                self._add_subscription_to_bucket(buckets, all_plan_key, subscription, closing_date)

        generated_at = fields.Datetime.now()
        values = []
        for (company_id, currency_id, plan_id), bucket in sorted(buckets.items()):
            trial_count = len(bucket['trial_ids'])
            if not trial_count:
                continue
            converted_count = len(bucket['converted_ids'])
            expired_count = len(bucket['expired_ids'])
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id or False,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id),
                'generated_at': generated_at,
                'status': 'ready',
                'trials_started_count': trial_count,
                'trials_converted_count': converted_count,
                'trials_expired_count': expired_count,
                'active_trial_count': len(bucket['active_trial_ids']),
                'converted_mrr': bucket['converted_mrr'],
                'active_trial_mrr': bucket['active_trial_mrr'],
                'conversion_rate': (converted_count / trial_count) * 100.0 if trial_count else 0.0,
                'expiry_rate': (expired_count / trial_count) * 100.0 if trial_count else 0.0,
                'average_trial_length_days': (
                    bucket['trial_days_total'] / bucket['trial_days_count']
                    if bucket['trial_days_count'] else 0.0
                ),
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None):
        self._check_trial_conversion_manager_access()
        opening_date = fields.Date.to_date(opening_date)
        closing_date = fields.Date.to_date(closing_date)
        if not opening_date or not closing_date:
            raise ValidationError(_("Opening and closing dates are required."))
        if opening_date > closing_date:
            raise ValidationError(_("Opening date must be on or before closing date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)

        self.search(self._prepare_existing_domain(opening_date, closing_date, company=company, plan=plan)).unlink()
        values = self._summary_values(opening_date, closing_date, company=company, plan=plan)
        return self.create(values) if values else self.browse()

    def _plan_domain(self):
        self.ensure_one()
        return [('subscription_plan_id', '=', self.subscription_plan_id.id)] if self.subscription_plan_id else [
            ('subscription_plan_id', '!=', False)
        ]

    def _base_trial_domain(self):
        self.ensure_one()
        return [
            ('is_subscription', '=', True),
            ('subscription_quote_type', '=', False),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('trial_start_date', '>=', self.opening_date),
            ('trial_start_date', '<=', self.closing_date),
        ] + self._plan_domain()

    def action_view_started_trials(self):
        self.ensure_one()
        return {
            'name': _('Started Trials'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._base_trial_domain(),
        }

    def action_view_converted_trials(self):
        self.ensure_one()
        return {
            'name': _('Converted Trials'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._base_trial_domain() + [
                ('subscription_start_date', '!=', False),
                ('subscription_state', 'not in', ['trial', 'cancelled', 'expired']),
            ],
        }

    def action_view_expired_trials(self):
        self.ensure_one()
        return {
            'name': _('Expired Trials'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._base_trial_domain() + [
                ('subscription_state', '=', 'expired'),
                ('subscription_start_date', '=', False),
                ('trial_end_date', '<=', self.closing_date),
            ],
        }

    def action_view_active_trials(self):
        self.ensure_one()
        return {
            'name': _('Active Trials'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._base_trial_domain() + [('subscription_state', '=', 'trial')],
        }
