from odoo import fields, models


class SubscriptionMrrMovement(models.Model):
    _name = 'subscription.mrr.movement'
    _description = 'Subscription MRR Movement'
    _order = 'movement_date desc, id desc'

    name = fields.Char(string='Description', required=True)
    movement_date = fields.Date(string='Movement Date', required=True, default=fields.Date.context_today, index=True)
    movement_type = fields.Selection([
        ('new', 'New MRR'),
        ('expansion', 'Expansion MRR'),
        ('contraction', 'Contraction MRR'),
        ('churn', 'Churned MRR'),
    ], string='Movement Type', required=True, index=True)

    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        required=True,
        ondelete='cascade',
        domain=[('is_subscription', '=', True)],
        index=True,
    )
    partner_id = fields.Many2one(related='subscription_id.partner_id', string='Customer', store=True, readonly=True)
    commercial_partner_id = fields.Many2one(
        related='subscription_id.partner_id.commercial_partner_id',
        string='Commercial Entity',
        store=True,
        readonly=True,
    )
    user_id = fields.Many2one(related='subscription_id.user_id', string='Salesperson', store=True, readonly=True)
    company_id = fields.Many2one(related='subscription_id.company_id', string='Company', store=True, readonly=True)
    subscription_plan_id = fields.Many2one(
        related='subscription_id.subscription_plan_id',
        string='Subscription Plan',
        store=True,
        readonly=True,
    )
    cancellation_reason_id = fields.Many2one(
        related='subscription_id.cancellation_reason_id',
        string='Cancellation Reason',
        store=True,
        readonly=True,
    )

    previous_mrr = fields.Monetary(string='Previous MRR', currency_field='currency_id', readonly=True)
    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', readonly=True)
    amount = fields.Monetary(string='Movement Amount', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='subscription_id.currency_id', string='Currency', store=True, readonly=True)
