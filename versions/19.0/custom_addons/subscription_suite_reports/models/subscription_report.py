from odoo import models, fields
from odoo.tools import drop_view_if_exists


class SubscriptionReport(models.Model):
    _name = 'subscription.report'
    _description = 'Subscription Analysis Report'
    _auto = False
    _order = 'date_order desc'

    name = fields.Char(string='Order Reference', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True)
    cancellation_reason_id = fields.Many2one('subscription.cancel.reason', string='Cancellation Reason', readonly=True)
    subscription_state = fields.Selection([
        ('draft', 'Draft'),
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='Status', readonly=True)
    
    recurring_total = fields.Monetary(string='Recurring Total', currency_field='currency_id', readonly=True)
    mrr = fields.Monetary(string='MRR', currency_field='currency_id', readonly=True)
    arr = fields.Monetary(string='ARR', currency_field='currency_id', readonly=True)
    active_mrr = fields.Monetary(string='Active MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    past_due_mrr = fields.Monetary(string='Past Due MRR', currency_field='currency_id', readonly=True)
    trial_mrr = fields.Monetary(string='Trial MRR', currency_field='currency_id', readonly=True)

    subscription_count = fields.Integer(string='Subscriptions', readonly=True)
    active_count = fields.Integer(string='Active Subscriptions', readonly=True)
    trial_count = fields.Integer(string='Trial Subscriptions', readonly=True)
    paused_count = fields.Integer(string='Paused Subscriptions', readonly=True)
    past_due_count = fields.Integer(string='Past Due Subscriptions', readonly=True)
    churned_count = fields.Integer(string='Churned Subscriptions', readonly=True)
    
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    subscription_start_date = fields.Date(string='Start Date', readonly=True)
    cancellation_date = fields.Date(string='Cancellation Date', readonly=True)
    country_id = fields.Many2one('res.country', string='Customer Country', readonly=True)
    commercial_partner_id = fields.Many2one('res.partner', string='Commercial Entity', readonly=True)
    
    def _select(self):
        return """
            SELECT
                s.id as id,
                s.name as name,
                s.date_order as date_order,
                s.partner_id as partner_id,
                s.user_id as user_id,
                s.company_id as company_id,
                s.subscription_plan_id as subscription_plan_id,
                s.cancellation_reason_id as cancellation_reason_id,
                s.subscription_state as subscription_state,
                s.recurring_total as recurring_total,
                s.mrr as mrr,
                s.mrr * 12 as arr,
                CASE WHEN s.subscription_state = 'active' THEN s.mrr ELSE 0 END as active_mrr,
                CASE WHEN s.subscription_state IN ('cancelled', 'expired') THEN s.mrr ELSE 0 END as churned_mrr,
                CASE WHEN s.subscription_state = 'past_due' THEN s.mrr ELSE 0 END as past_due_mrr,
                CASE WHEN s.subscription_state = 'trial' THEN s.mrr ELSE 0 END as trial_mrr,
                1 as subscription_count,
                CASE WHEN s.subscription_state = 'active' THEN 1 ELSE 0 END as active_count,
                CASE WHEN s.subscription_state = 'trial' THEN 1 ELSE 0 END as trial_count,
                CASE WHEN s.subscription_state = 'paused' THEN 1 ELSE 0 END as paused_count,
                CASE WHEN s.subscription_state = 'past_due' THEN 1 ELSE 0 END as past_due_count,
                CASE WHEN s.subscription_state IN ('cancelled', 'expired') THEN 1 ELSE 0 END as churned_count,
                s.currency_id as currency_id,
                s.subscription_start_date as subscription_start_date,
                s.cancellation_date as cancellation_date,
                p.country_id as country_id,
                p.commercial_partner_id as commercial_partner_id
        """

    def _from(self):
        return """
            FROM sale_order s
            JOIN res_partner p ON (s.partner_id = p.id)
        """

    def _where(self):
        return """
            WHERE s.is_subscription = true
        """

    def init(self):
        # Tools to create or replace the database view
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (
            %s
            %s
            %s
            )""" % (self._table, self._select(), self._from(), self._where()))
