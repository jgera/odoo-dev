from odoo import _, fields, models
from odoo.exceptions import ValidationError


class SubscriptionDeferredRevenueWizard(models.TransientModel):
    _name = 'subscription.deferred.revenue.wizard'
    _description = 'Generate Subscription Deferred Revenue Schedules'

    date_from = fields.Date(string='Invoice Date From')
    date_to = fields.Date(string='Invoice Date To')
    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        domain=[('is_subscription', '=', True)],
    )
    recognition_method = fields.Selection(
        [
            ('straight_line_daily', 'Straight-line Daily'),
            ('equal_monthly', 'Equal Monthly'),
        ],
        string='Recognition Method',
        default=lambda self: self.env['subscription.deferred.revenue']._get_default_recognition_method(),
        required=True,
    )

    def _invoice_domain(self):
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('subscription_id', '!=', False),
        ]
        if self.date_from:
            domain.append(('invoice_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('invoice_date', '<=', self.date_to))
        if self.subscription_id:
            domain.append(('subscription_id', '=', self.subscription_id.id))
        return domain

    def action_generate(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_('Invoice Date From must be before Invoice Date To.'))
        invoices = self.env['account.move'].search(self._invoice_domain())
        schedules = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoices,
            method=self.recognition_method,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Schedules'),
            'res_model': 'subscription.deferred.revenue',
            'view_mode': 'list,form',
            'domain': [('id', 'in', schedules.ids)],
            'context': {'search_default_group_state': 1},
        }
