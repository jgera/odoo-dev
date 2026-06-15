from odoo import api, fields, models


class SubscriptionUsageMeter(models.Model):
    _name = 'subscription.usage.meter'
    _description = 'Subscription Usage Meter'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, copy=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _code_company_unique = models.Constraint(
        'UNIQUE(code, company_id)',
        'Usage meter code must be unique per company.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().write(vals)
