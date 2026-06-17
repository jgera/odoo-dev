from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SubscriptionMrrKpiSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.mrr.kpi.summary.generate.wizard'
    _description = 'Generate MRR KPI Summary'

    opening_date = fields.Date(string='Opening Date', required=True)
    closing_date = fields.Date(string='Closing Date', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help="Leave empty to generate KPI summaries for all accessible companies.",
    )
    subscription_plan_id = fields.Many2one(
        'subscription.plan',
        string='Subscription Plan',
        help="Leave empty to generate KPI summaries for all plans.",
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_date_range(self):
        for wizard in self:
            if wizard.opening_date and wizard.closing_date and wizard.opening_date >= wizard.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    def action_generate_summary(self):
        self.ensure_one()
        Summary = self.env['subscription.mrr.kpi.summary']
        Summary.generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        domain = [('opening_date', '=', self.opening_date), ('closing_date', '=', self.closing_date)]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return {
            'name': _('MRR KPI Summary'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.kpi.summary',
            'view_mode': 'list,form,pivot,graph',
            'domain': domain,
            'target': 'current',
        }
