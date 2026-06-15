from odoo import models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_recurring = fields.Boolean(string='Is Recurring', default=False)
    subscription_component_type = fields.Selection([
        ('base', 'Base'),
        ('seat', 'Seat'),
        ('addon', 'Add-on'),
    ], string='Subscription Component', default='base', required=True)
    recurring_interval_count = fields.Integer(string='Recurring Interval Count')
    recurring_interval_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years')
    ], string='Recurring Interval Unit')
