from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    proration_id = fields.Many2one('subscription.proration', string='Proration Record', readonly=True)
    usage_summary_ids = fields.One2many(
        'subscription.usage.summary',
        'invoice_id',
        string='Usage Summaries',
        readonly=True,
    )


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    usage_summary_id = fields.Many2one(
        'subscription.usage.summary',
        string='Usage Summary',
        readonly=True,
        copy=False,
    )
