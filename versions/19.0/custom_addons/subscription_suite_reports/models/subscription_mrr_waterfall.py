from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionMrrWaterfall(models.Model):
    _name = 'subscription.mrr.waterfall'
    _description = 'Subscription MRR Waterfall'
    _order = 'closing_date desc, opening_date desc, company_id, currency_id, subscription_plan_id, bucket_sequence'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([
        ('ready', 'Ready'),
        ('variance', 'Variance'),
        ('missing_kpi_summary', 'Missing KPI Summary'),
        ('missing_inputs', 'Missing Inputs'),
    ], string='Status', required=True, readonly=True, index=True)
    source_count = fields.Integer(string='Source KPI Summaries', readonly=True)

    bucket_sequence = fields.Integer(string='Sequence', required=True, readonly=True, index=True)
    bucket_type = fields.Selection([
        ('opening', 'Opening MRR'),
        ('new', 'New MRR'),
        ('expansion', 'Expansion MRR'),
        ('contraction', 'Contraction MRR'),
        ('churn', 'Churned MRR'),
        ('closing', 'Closing MRR'),
    ], string='Bucket Type', required=True, readonly=True, index=True)
    bucket_label = fields.Char(string='Bucket', required=True, readonly=True)
    amount = fields.Monetary(string='Amount', currency_field='currency_id', readonly=True)
    starting_mrr = fields.Monetary(string='Starting MRR', currency_field='currency_id', readonly=True)
    ending_mrr = fields.Monetary(string='Ending MRR', currency_field='currency_id', readonly=True)
    expected_closing_mrr = fields.Monetary(string='Expected Closing MRR', currency_field='currency_id', readonly=True)
    actual_closing_mrr = fields.Monetary(string='Actual Closing MRR', currency_field='currency_id', readonly=True)
    variance_mrr = fields.Monetary(string='Variance', currency_field='currency_id', readonly=True)

    _mrr_waterfall_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key, bucket_type)',
        'Only one MRR waterfall bucket can exist for the same date range, scope, and bucket type.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_date_range(self):
        for waterfall in self:
            if waterfall.opening_date >= waterfall.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_waterfall_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate MRR waterfalls."))

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id=False):
        return '%s:%s:%s' % (company_id, currency_id, plan_id or 'all_plans')

    @api.model
    def _prepare_waterfall_domain(self, opening_date, closing_date, company, currency, plan=None):
        domain = [
            ('opening_date', '=', opening_date),
            ('closing_date', '=', closing_date),
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
        ]
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        else:
            domain.append(('subscription_plan_id', '=', False))
        return domain

    @api.model
    def _prepare_summary_domain(self, opening_date, closing_date, company, currency, plan=None):
        domain = [
            ('opening_date', '=', opening_date),
            ('closing_date', '=', closing_date),
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
        ]
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _aggregate_summaries(self, summaries):
        values = {
            'source_count': len(summaries),
            'opening_mrr': 0.0,
            'closing_mrr': 0.0,
            'new_mrr': 0.0,
            'expansion_mrr': 0.0,
            'contraction_mrr': 0.0,
            'churned_mrr': 0.0,
        }
        for summary in summaries:
            values['opening_mrr'] += summary.opening_mrr or 0.0
            values['closing_mrr'] += summary.closing_mrr or 0.0
            values['new_mrr'] += summary.new_mrr or 0.0
            values['expansion_mrr'] += summary.expansion_mrr or 0.0
            values['contraction_mrr'] += summary.contraction_mrr or 0.0
            values['churned_mrr'] += summary.churned_mrr or 0.0
        return values

    @api.model
    def _waterfall_rows(self, opening_date, closing_date, company, currency, plan=None):
        summaries = self.env['subscription.mrr.kpi.summary'].search(
            self._prepare_summary_domain(opening_date, closing_date, company, currency, plan=plan)
        )
        totals = self._aggregate_summaries(summaries)
        expected_closing = (
            totals['opening_mrr']
            + totals['new_mrr']
            + totals['expansion_mrr']
            + totals['contraction_mrr']
            + totals['churned_mrr']
        )
        actual_closing = totals['closing_mrr']
        variance = actual_closing - expected_closing
        status = 'missing_kpi_summary'
        if summaries:
            if not all(summary.status == 'ready' for summary in summaries):
                status = 'missing_inputs'
            elif currency.compare_amounts(variance, 0.0):
                status = 'variance'
            else:
                status = 'ready'
        generated_at = fields.Datetime.now()
        bucket_key = self._bucket_key(company.id, currency.id, plan.id if plan else False)
        scope_values = {
            'opening_date': opening_date,
            'closing_date': closing_date,
            'company_id': company.id,
            'currency_id': currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': bucket_key,
            'generated_at': generated_at,
            'status': status,
            'source_count': totals['source_count'],
            'expected_closing_mrr': expected_closing,
            'actual_closing_mrr': actual_closing,
            'variance_mrr': variance,
        }
        running = totals['opening_mrr']
        rows = [{
            **scope_values,
            'bucket_sequence': 10,
            'bucket_type': 'opening',
            'bucket_label': _('01 Opening MRR'),
            'amount': totals['opening_mrr'],
            'starting_mrr': 0.0,
            'ending_mrr': totals['opening_mrr'],
        }]
        for sequence, bucket_type, label, amount in (
            (20, 'new', _('02 New MRR'), totals['new_mrr']),
            (30, 'expansion', _('03 Expansion MRR'), totals['expansion_mrr']),
            (40, 'contraction', _('04 Contraction MRR'), totals['contraction_mrr']),
            (50, 'churn', _('05 Churned MRR'), totals['churned_mrr']),
        ):
            start = running
            running += amount
            rows.append({
                **scope_values,
                'bucket_sequence': sequence,
                'bucket_type': bucket_type,
                'bucket_label': label,
                'amount': amount,
                'starting_mrr': start,
                'ending_mrr': running,
            })
        rows.append({
            **scope_values,
            'bucket_sequence': 60,
            'bucket_type': 'closing',
            'bucket_label': _('06 Closing MRR'),
            'amount': totals['closing_mrr'],
            'starting_mrr': 0.0,
            'ending_mrr': totals['closing_mrr'],
        })
        return rows

    @api.model
    def generate_for_period(self, opening_date, closing_date, company, currency, plan=None):
        self._check_waterfall_manager_access()
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(currency, int):
            currency = self.env['res.currency'].browse(currency)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        if not company or not currency:
            raise ValidationError(_("Company and currency are required for MRR waterfalls."))
        self.search(
            self._prepare_waterfall_domain(opening_date, closing_date, company, currency, plan=plan)
        ).unlink()
        return self.create(self._waterfall_rows(opening_date, closing_date, company, currency, plan=plan))

    def _scope_domain(self):
        self.ensure_one()
        domain = [
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def action_view_kpi_summaries(self):
        self.ensure_one()
        return {
            'name': _('MRR KPI Summaries'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.kpi.summary',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._scope_domain(),
        }

    def action_view_snapshots(self):
        self.ensure_one()
        domain = [
            ('snapshot_date', 'in', [self.opening_date, self.closing_date]),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return {
            'name': _('MRR Snapshots'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.snapshot',
            'view_mode': 'list,form,pivot,graph',
            'domain': domain,
        }

    def action_view_movements(self):
        self.ensure_one()
        domain = [
            ('movement_date', '>', self.opening_date),
            ('movement_date', '<=', self.closing_date),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        movement_type = {
            'new': 'new',
            'expansion': 'expansion',
            'contraction': 'contraction',
            'churn': 'churn',
        }.get(self.bucket_type)
        if movement_type:
            domain.append(('movement_type', '=', movement_type))
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return {
            'name': _('MRR Movements'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.movement',
            'view_mode': 'list,form,pivot,graph',
            'domain': domain,
        }

    def action_view_sources(self):
        self.ensure_one()
        if self.bucket_type in ('opening', 'closing'):
            return self.action_view_snapshots()
        return self.action_view_movements()
