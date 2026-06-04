from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    proration_id = fields.Many2one('subscription.proration', string='Proration Record', readonly=True)
