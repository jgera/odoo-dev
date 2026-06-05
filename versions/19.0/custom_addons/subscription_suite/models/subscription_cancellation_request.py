from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SubscriptionCancellationRequest(models.Model):
    _name = 'subscription.cancellation.request'
    _description = 'Subscription Cancellation Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'subscription.request.mixin']
    _order = 'requested_on desc, id desc'

    name = fields.Char(default=lambda self: _('New'), copy=False, readonly=True)
    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, ondelete='cascade', tracking=True)
    partner_id = fields.Many2one(related='subscription_id.partner_id', store=True)
    reason_id = fields.Many2one('subscription.cancel.reason', string='Reason', required=True, readonly=True)
    feedback = fields.Text(readonly=True)
    requested_effective_date = fields.Date(string='Effective Date', required=True, readonly=True)
    requested_policy = fields.Selection([
        ('immediate', 'Immediate'),
        ('end_of_period', 'End of Billing Period'),
    ], string='Policy', required=True, readonly=True)
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
    company_id = fields.Many2one(related='subscription_id.company_id', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('name', _('New')) == _('New'):
                values['name'] = self.env['ir.sequence'].next_by_code('subscription.cancellation.request') or _('New')
        requests = super().create(vals_list)
        requests._schedule_manager_review_activity()
        return requests

    def _ensure_manager(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise UserError(_('Only subscription managers can approve or reject cancellation requests.'))

    def _ensure_pending(self):
        for request in self:
            if request.state != 'pending':
                raise ValidationError(_('Only pending cancellation requests can be processed.'))

    def action_approve(self):
        self._ensure_manager()
        for request in self:
            request._ensure_pending()
            subscription = request.subscription_id
            if subscription.pending_cancellation:
                raise ValidationError(_('This subscription already has a scheduled cancellation.'))
            if subscription.subscription_state in ['cancelled', 'expired']:
                raise ValidationError(_('Cancelled or expired subscriptions cannot be cancelled again.'))

            if request.requested_policy == 'end_of_period':
                subscription._action_schedule_cancel(
                    reason_id=request.reason_id.id,
                    feedback=request.feedback,
                    effective_date=request.requested_effective_date,
                    policy=request.requested_policy,
                )
            else:
                subscription._action_cancel(
                    reason_id=request.reason_id.id,
                    feedback=request.feedback,
                    cancellation_date=request.requested_effective_date,
                    cancellation_policy=request.requested_policy,
                )
            request.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approved_on': fields.Datetime.now(),
            })
            request._close_manager_review_activity(_('Cancellation request approved.'))
            subscription._log_subscription_event(
                'cancellation_requested',
                _('Cancellation request %(request)s approved', request=request.name),
                new_values={'request_id': request.id, 'policy': request.requested_policy},
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
            request._close_manager_review_activity(_('Cancellation request rejected.'))
            request.subscription_id._log_subscription_event(
                'cancellation_requested',
                _('Cancellation request %(request)s rejected', request=request.name),
                old_values={'request_id': request.id, 'reason': request.reason_id.display_name},
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
            request._close_manager_review_activity(_('Cancellation request cancelled.'))
            request.subscription_id.sudo()._log_subscription_event(
                'cancellation_requested',
                _('Cancellation request %(request)s cancelled', request=request.name),
                old_values={'request_id': request.id, 'reason': request.reason_id.display_name},
            )
        return True
