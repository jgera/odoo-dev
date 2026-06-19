from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    proration_id = fields.Many2one('subscription.proration', string='Proration Record', readonly=True)
    deferred_revenue_schedule_ids = fields.One2many(
        'subscription.deferred.revenue',
        'invoice_id',
        string='Deferred Revenue Schedules',
        readonly=True,
    )
    deferred_revenue_schedule_count = fields.Integer(compute='_compute_deferred_revenue_schedule_count')
    usage_summary_ids = fields.One2many(
        'subscription.usage.summary',
        'invoice_id',
        string='Usage Summaries',
        readonly=True,
    )

    def _compute_deferred_revenue_schedule_count(self):
        groups = self.env['subscription.deferred.revenue'].read_group(
            [('invoice_id', 'in', self.ids)],
            ['invoice_id'],
            ['invoice_id'],
        )
        counts = {group['invoice_id'][0]: group['invoice_id_count'] for group in groups}
        for move in self:
            move.deferred_revenue_schedule_count = counts.get(move.id, 0)

    def action_view_deferred_revenue_schedules(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Deferred Revenue Schedules',
            'res_model': 'subscription.deferred.revenue',
            'view_mode': 'list,form',
            'domain': [('invoice_id', '=', self.id)],
            'context': {'default_invoice_id': self.id},
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    usage_summary_id = fields.Many2one(
        'subscription.usage.summary',
        string='Usage Summary',
        readonly=True,
        copy=False,
    )
