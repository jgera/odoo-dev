from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionMrrKpiDashboard(models.Model):
    _name = 'subscription.mrr.kpi.dashboard'
    _description = 'Subscription MRR KPI Dashboard'
    _order = 'closing_date desc, opening_date desc, company_id, currency_id, subscription_plan_id'

    name = fields.Char(string='Dashboard', required=True, readonly=True)
    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([
        ('ready', 'Ready'),
        ('missing_kpi_summary', 'Missing KPI Summary'),
        ('missing_inputs', 'Missing Inputs'),
    ], string='Status', required=True, readonly=True, index=True)
    summary_count = fields.Integer(string='Source KPI Summaries', readonly=True)

    opening_mrr = fields.Monetary(string='Opening MRR', currency_field='currency_id', readonly=True)
    closing_mrr = fields.Monetary(string='Closing MRR', currency_field='currency_id', readonly=True)
    snapshot_delta_mrr = fields.Monetary(string='Snapshot Delta', currency_field='currency_id', readonly=True)
    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', readonly=True)
    expansion_mrr = fields.Monetary(string='Expansion MRR', currency_field='currency_id', readonly=True)
    contraction_mrr = fields.Monetary(string='Contraction MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    net_new_mrr = fields.Monetary(string='Net New MRR', currency_field='currency_id', readonly=True)
    nrr = fields.Float(string='NRR (%)', readonly=True)
    grr = fields.Float(string='GRR (%)', readonly=True)
    variance_mrr = fields.Monetary(string='Reconciliation Variance', currency_field='currency_id', readonly=True)

    _kpi_dashboard_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one MRR KPI dashboard can exist for the same date range and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_date_range(self):
        for dashboard in self:
            if dashboard.opening_date >= dashboard.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_dashboard_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate MRR KPI dashboards."))

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id=False):
        return '%s:%s:%s' % (company_id, currency_id, plan_id or 'all_plans')

    @api.model
    def _prepare_dashboard_domain(self, opening_date, closing_date, company, currency, plan=None):
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
    def _dashboard_name(self, opening_date, closing_date, company, currency, plan=None):
        scope = plan.display_name if plan else _('All Plans')
        return _('%(start)s to %(end)s - %(company)s - %(currency)s - %(scope)s',
                 start=opening_date, end=closing_date, company=company.display_name,
                 currency=currency.name, scope=scope)

    @api.model
    def _aggregate_summaries(self, summaries):
        values = {
            'summary_count': len(summaries),
            'opening_mrr': 0.0,
            'closing_mrr': 0.0,
            'snapshot_delta_mrr': 0.0,
            'new_mrr': 0.0,
            'expansion_mrr': 0.0,
            'contraction_mrr': 0.0,
            'churned_mrr': 0.0,
            'net_new_mrr': 0.0,
            'variance_mrr': 0.0,
        }
        for summary in summaries:
            for field_name in (
                'opening_mrr',
                'closing_mrr',
                'snapshot_delta_mrr',
                'new_mrr',
                'expansion_mrr',
                'contraction_mrr',
                'churned_mrr',
                'net_new_mrr',
                'variance_mrr',
            ):
                values[field_name] += summary[field_name] or 0.0
        values['nrr'] = 0.0
        values['grr'] = 0.0
        if values['opening_mrr']:
            values['nrr'] = (
                (
                    values['opening_mrr']
                    + values['expansion_mrr']
                    + values['contraction_mrr']
                    + values['churned_mrr']
                )
                / values['opening_mrr']
            ) * 100.0
            values['grr'] = (
                (
                    values['opening_mrr']
                    + values['contraction_mrr']
                    + values['churned_mrr']
                )
                / values['opening_mrr']
            ) * 100.0
        return values

    @api.model
    def _get_dashboard_values(self, opening_date, closing_date, company, currency, plan=None):
        summaries = self.env['subscription.mrr.kpi.summary'].search(
            self._prepare_summary_domain(opening_date, closing_date, company, currency, plan=plan)
        )
        values = {
            'name': self._dashboard_name(opening_date, closing_date, company, currency, plan=plan),
            'opening_date': opening_date,
            'closing_date': closing_date,
            'company_id': company.id,
            'currency_id': currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': self._bucket_key(company.id, currency.id, plan.id if plan else False),
            'generated_at': fields.Datetime.now(),
        }
        if not summaries:
            values.update({
                'status': 'missing_kpi_summary',
                'summary_count': 0,
                'opening_mrr': 0.0,
                'closing_mrr': 0.0,
                'snapshot_delta_mrr': 0.0,
                'new_mrr': 0.0,
                'expansion_mrr': 0.0,
                'contraction_mrr': 0.0,
                'churned_mrr': 0.0,
                'net_new_mrr': 0.0,
                'variance_mrr': 0.0,
                'nrr': 0.0,
                'grr': 0.0,
            })
            return values
        values.update(self._aggregate_summaries(summaries))
        values['status'] = 'ready' if all(summary.status == 'ready' for summary in summaries) else 'missing_inputs'
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company, currency, plan=None):
        self._check_dashboard_manager_access()
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(currency, int):
            currency = self.env['res.currency'].browse(currency)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        if not company or not currency:
            raise ValidationError(_("Company and currency are required for MRR KPI dashboards."))
        self.search(
            self._prepare_dashboard_domain(opening_date, closing_date, company, currency, plan=plan)
        ).unlink()
        return self.create(self._get_dashboard_values(opening_date, closing_date, company, currency, plan=plan))

    def _source_domain(self, include_plan=True):
        self.ensure_one()
        domain = [
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if include_plan and self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def action_view_kpi_summaries(self):
        self.ensure_one()
        return {
            'name': _('MRR KPI Summaries'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.kpi.summary',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._source_domain(),
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

    def action_view_reconciliations(self):
        self.ensure_one()
        return {
            'name': _('MRR Reconciliations'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.reconciliation',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._source_domain(),
        }

    def action_view_anomalies(self):
        self.ensure_one()
        return {
            'name': _('MRR Movement Anomalies'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.movement.anomaly',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._source_domain(),
        }

    def action_view_movements(self):
        self.ensure_one()
        domain = [
            ('movement_date', '>', self.opening_date),
            ('movement_date', '<=', self.closing_date),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return {
            'name': _('MRR Movements'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.movement',
            'view_mode': 'list,form,pivot,graph',
            'domain': domain,
        }
