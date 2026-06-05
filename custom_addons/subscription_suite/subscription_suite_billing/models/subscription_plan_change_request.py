from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SubscriptionPlanChangeRequest(models.Model):
    _name = 'subscription.plan.change.request'
    _description = 'Subscription Plan Change Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'subscription.request.mixin']
    _order = 'create_date desc'

    name = fields.Char(default=lambda self: _('New'), copy=False, readonly=True)
    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, ondelete='cascade', tracking=True)
    partner_id = fields.Many2one(related='subscription_id.partner_id', store=True)
    current_plan_id = fields.Many2one('subscription.plan', string='Current Plan', required=True, readonly=True)
    requested_plan_id = fields.Many2one('subscription.plan', string='Requested Plan', required=True, readonly=True)
    requested_effective_date = fields.Date(string='Effective Date', required=True, readonly=True)
    requested_timing = fields.Selection([
        ('immediate', 'Immediately with Proration'),
        ('next_period', 'Next Billing Period'),
    ], string='Apply', required=True, readonly=True)
    change_type = fields.Selection([
        ('upgrade', 'Upgrade'),
        ('downgrade', 'Downgrade'),
    ], required=True, readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, tracking=True)
    requested_by_id = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user, readonly=True)
    requested_on = fields.Datetime(string='Requested On', default=fields.Datetime.now, readonly=True)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_on = fields.Datetime(string='Approved On', readonly=True)
    rejected_by_id = fields.Many2one('res.users', string='Rejected By', readonly=True)
    rejected_on = fields.Datetime(string='Rejected On', readonly=True)
    rejection_reason = fields.Text()
    old_mrr = fields.Monetary(string='Current MRR', currency_field='currency_id', readonly=True)
    new_mrr = fields.Monetary(string='Requested MRR', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='subscription_id.currency_id', store=True)
    company_id = fields.Many2one(related='subscription_id.company_id', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('name', _('New')) == _('New'):
                values['name'] = self.env['ir.sequence'].next_by_code('subscription.plan.change.request') or _('New')
        requests = super().create(vals_list)
        requests._schedule_manager_review_activity()
        return requests

    def _ensure_manager(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise UserError(_('Only subscription managers can approve or reject plan change requests.'))

    def _ensure_pending(self):
        for request in self:
            if request.state != 'pending':
                raise ValidationError(_('Only pending plan change requests can be processed.'))

    def action_approve(self):
        self._ensure_manager()
        for request in self:
            request._ensure_pending()
            subscription = request.subscription_id.with_context(bypass_plan_change_approval=True)
            if request.requested_timing == 'next_period':
                subscription._schedule_plan_change(
                    request.requested_plan_id,
                    effective_date=request.requested_effective_date,
                )
            else:
                subscription._execute_plan_change(
                    request.requested_plan_id,
                    effective_date=request.requested_effective_date,
                )
            request.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approved_on': fields.Datetime.now(),
            })
            request._close_manager_review_activity(_('Plan change request approved.'))
            request.subscription_id._log_subscription_event(
                'plan_changed',
                _('Plan change request %(request)s approved', request=request.name),
                new_values={'request_id': request.id, 'requested_plan': request.requested_plan_id.display_name},
            )
        return True

    def action_reject(self):
        self._ensure_manager()
        for request in self:
            request._ensure_pending()
            request.write({
                'state': 'rejected',
                'rejected_by_id': self.env.user.id,
                'rejected_on': fields.Datetime.now(),
            })
            request._close_manager_review_activity(_('Plan change request rejected.'))
            request.subscription_id._log_subscription_event(
                'plan_changed',
                _('Plan change request %(request)s rejected', request=request.name),
                old_values={'request_id': request.id, 'requested_plan': request.requested_plan_id.display_name},
            )
        return True

    def action_cancel(self):
        for request in self:
            if request.state != 'pending':
                continue
            if (
                request.requested_by_id != self.env.user
                and not self.env.user.has_group('subscription_suite.group_subscription_manager')
            ):
                raise UserError(_('Only the requester or a subscription manager can cancel this request.'))
            request.state = 'cancelled'
            request._close_manager_review_activity(_('Plan change request cancelled.'))
            request.subscription_id.sudo()._log_subscription_event(
                'plan_changed',
                _('Plan change request %(request)s cancelled', request=request.name),
                old_values={'request_id': request.id, 'requested_plan': request.requested_plan_id.display_name},
            )
        return True
