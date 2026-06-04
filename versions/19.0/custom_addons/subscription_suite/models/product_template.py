from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_subscription_product = fields.Boolean(string='Is Subscription Product')
    subscription_plan_ids = fields.Many2many(
        'subscription.plan',
        'product_subscription_plan_rel',
        'product_tmpl_id',
        'plan_id',
        string='Available in Plans'
    )
