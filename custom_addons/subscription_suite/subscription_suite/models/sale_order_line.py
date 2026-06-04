from odoo import models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_recurring = fields.Boolean(string='Is Recurring', default=False)
    recurring_interval_count = fields.Integer(string='Recurring Interval Count')
    recurring_interval_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years')
    ], string='Recurring Interval Unit')
