import logging
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_subscription = fields.Boolean(string='Is Subscription', default=False)
    subscription_state = fields.Selection([
        ('draft', 'Draft'),
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='Subscription Status', default='draft', copy=False, tracking=True)
    
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')
    subscription_code = fields.Char(string='Subscription Code', copy=False, readonly=True)
    subscription_quote_type = fields.Selection([
        ('renewal', 'Renewal'),
        ('upsell', 'Upsell'),
    ], string='Subscription Quote Type', copy=False, index=True)
    subscription_origin_id = fields.Many2one(
        'sale.order',
        string='Origin Subscription',
        copy=False,
        index=True,
        domain=[('is_subscription', '=', True)],
    )
    subscription_quote_effective_date = fields.Date(string='Quote Effective Date', copy=False)
    subscription_quote_ids = fields.One2many(
        'sale.order',
        'subscription_origin_id',
        string='Subscription Quotes',
    )
    subscription_quote_count = fields.Integer(
        string='Sales History',
        compute='_compute_subscription_quote_count',
    )
    cancellation_request_count = fields.Integer(
        string='Cancellation Requests',
        compute='_compute_subscription_request_counts',
    )
    lifecycle_request_count = fields.Integer(
        string='Lifecycle Requests',
        compute='_compute_subscription_request_counts',
    )
    
    trial_start_date = fields.Date(string='Trial Start Date', copy=False)
    trial_end_date = fields.Date(string='Trial End Date', copy=False)
    subscription_start_date = fields.Date(string='Subscription Start Date', copy=False)
    subscription_end_date = fields.Date(string='Subscription End Date', copy=False)
    
    next_invoice_date = fields.Date(string='Next Invoice Date', copy=False)
    last_invoice_date = fields.Date(string='Last Invoice Date', copy=False)
    
    billing_interval_count = fields.Integer(string='Billing Interval Count', default=1)
    billing_interval_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years')
    ], string='Billing Interval Unit', default='month')
    
    payment_token_id = fields.Many2one('payment.token', string='Payment Token', copy=False)
    
    recurring_total = fields.Monetary(string='Recurring Total', compute='_compute_recurring_total', store=True)
    mrr = fields.Monetary(string='MRR', compute='_compute_mrr', store=True)
    
    pause_date = fields.Date(string='Pause Date', copy=False)
    resume_date = fields.Date(string='Resume Date', copy=False)
    cancellation_date = fields.Date(string='Cancellation Date', copy=False)
    cancellation_requested_date = fields.Date(string='Cancellation Requested Date', copy=False)
    cancellation_effective_date = fields.Date(string='Cancellation Effective Date', copy=False, index=True)
    cancellation_policy_applied = fields.Selection([
        ('immediate', 'Immediate'),
        ('end_of_period', 'End of Billing Period'),
    ], string='Cancellation Policy Applied', copy=False)
    pending_cancellation = fields.Boolean(string='Pending Cancellation', copy=False, index=True)
    
    cancellation_reason_id = fields.Many2one('subscription.cancel.reason', string='Cancellation Reason', copy=False)
    cancellation_feedback = fields.Text(string='Cancellation Feedback', copy=False)
    
    subscription_log_ids = fields.One2many('subscription.log', 'subscription_id', string='Subscription Logs')
    
    health_score = fields.Selection([
        ('good', 'Good'),
        ('at_risk', 'At Risk'),
        ('churning', 'Churning')
    ], string='Health Score', compute='_compute_health_score', store=True)
    
    is_auto_pay = fields.Boolean(string='Is Auto Pay', compute='_compute_is_auto_pay')
    days_since_start = fields.Integer(string='Days Since Start', compute='_compute_days_since_start')
    current_period_start = fields.Date(string='Current Period Start', compute='_compute_current_period')
    current_period_end = fields.Date(string='Current Period End', compute='_compute_current_period')

    def _compute_subscription_quote_count(self):
        grouped = self.env['sale.order']._read_group(
            [('subscription_origin_id', 'in', self.ids)],
            ['subscription_origin_id'],
            ['__count'],
        )
        counts = {subscription.id: count for subscription, count in grouped}
        for order in self:
            order.subscription_quote_count = counts.get(order.id, 0)

    def _compute_subscription_request_counts(self):
        cancellation_grouped = self.env['subscription.cancellation.request']._read_group(
            [('subscription_id', 'in', self.ids)],
            ['subscription_id'],
            ['__count'],
        )
        lifecycle_grouped = self.env['subscription.lifecycle.request']._read_group(
            [('subscription_id', 'in', self.ids)],
            ['subscription_id'],
            ['__count'],
        )
        cancellation_counts = {subscription.id: count for subscription, count in cancellation_grouped}
        lifecycle_counts = {subscription.id: count for subscription, count in lifecycle_grouped}
        for order in self:
            order.cancellation_request_count = cancellation_counts.get(order.id, 0)
            order.lifecycle_request_count = lifecycle_counts.get(order.id, 0)

    @api.depends('order_line.price_subtotal', 'order_line.is_recurring')
    def _compute_recurring_total(self):
        for order in self:
            recurring_lines = order.order_line.filtered(lambda l: l.is_recurring)
            order.recurring_total = sum(recurring_lines.mapped('price_subtotal'))

    @api.depends('recurring_total', 'billing_interval_count', 'billing_interval_unit')
    def _compute_mrr(self):
        for order in self:
            amount = order.recurring_total
            count = order.billing_interval_count or 1
            unit = order.billing_interval_unit
            if unit == 'day':
                order.mrr = (amount / count) * 30
            elif unit == 'week':
                order.mrr = (amount / count) * 4.33
            elif unit == 'month':
                order.mrr = amount / count
            elif unit == 'year':
                order.mrr = amount / (12 * count)
            else:
                order.mrr = 0.0

    @api.depends('subscription_state', 'payment_token_id', 'is_subscription')
    def _compute_health_score(self):
        for order in self:
            if order.subscription_state == 'past_due':
                order.health_score = 'churning'
            elif order.subscription_state in ['cancelled', 'expired']:
                order.health_score = 'good'
            elif not order.payment_token_id and order.is_subscription:
                order.health_score = 'at_risk'
            else:
                order.health_score = 'good'

    @api.depends('payment_token_id')
    def _compute_is_auto_pay(self):
        for order in self:
            order.is_auto_pay = bool(order.payment_token_id)

    @api.depends('subscription_start_date', 'trial_start_date')
    def _compute_days_since_start(self):
        today = fields.Date.today()
        for order in self:
            start_date = order.subscription_start_date or order.trial_start_date
            if start_date and start_date <= today:
                order.days_since_start = (today - start_date).days
            else:
                order.days_since_start = 0

    @api.depends('last_invoice_date', 'next_invoice_date')
    def _compute_current_period(self):
        for order in self:
            order.current_period_start = order.last_invoice_date
            order.current_period_end = order.next_invoice_date

    @api.onchange('subscription_plan_id')
    def _onchange_subscription_plan_id(self):
        if self.subscription_plan_id:
            self.billing_interval_count = self.subscription_plan_id.billing_interval_count
            self.billing_interval_unit = self.subscription_plan_id.billing_interval_unit
            # Note: Populating order lines based on plan lines would go here.

    def _log_subscription_event(self, event_type, description, old_values=None, new_values=None):
        self.ensure_one()
        self.env['subscription.log'].create({
            'subscription_id': self.id,
            'event_type': event_type,
            'description': description,
            'old_value': str(old_values) if old_values else False,
            'new_value': str(new_values) if new_values else False,
        })

    def _log_mrr_movement(self, movement_type, previous_mrr=0.0, new_mrr=0.0, description=None, movement_date=None):
        self.ensure_one()
        if not self.is_subscription:
            return False

        previous_mrr = previous_mrr or 0.0
        new_mrr = new_mrr or 0.0
        amount = new_mrr - previous_mrr
        if not amount:
            return False

        return self.env['subscription.mrr.movement'].create({
            'name': description or dict(self.env['subscription.mrr.movement']._fields['movement_type'].selection).get(movement_type),
            'movement_date': movement_date or fields.Date.today(),
            'movement_type': movement_type,
            'subscription_id': self.id,
            'previous_mrr': previous_mrr,
            'new_mrr': new_mrr,
            'amount': amount,
        })

    def _get_commitment_start_date(self):
        self.ensure_one()
        return self.subscription_start_date or self.trial_start_date

    def _get_commitment_end_date(self):
        self.ensure_one()
        plan = self.subscription_plan_id
        start_date = self._get_commitment_start_date()
        periods = plan.min_commitment_periods if plan else 0
        if not start_date or not periods:
            return False

        interval_count = plan.billing_interval_count * periods
        interval_unit = plan.billing_interval_unit
        if interval_unit == 'day':
            return start_date + relativedelta(days=interval_count)
        if interval_unit == 'week':
            return start_date + relativedelta(weeks=interval_count)
        if interval_unit == 'month':
            return start_date + relativedelta(months=interval_count)
        if interval_unit == 'year':
            return start_date + relativedelta(years=interval_count)
        return False

    def _check_minimum_commitment(self, action_label=None, effective_date=None):
        self.ensure_one()
        commitment_end_date = self._get_commitment_end_date()
        if not commitment_end_date:
            return True

        effective_date = effective_date or fields.Date.today()
        if effective_date < commitment_end_date:
            action_label = action_label or _('This action')
            raise UserError(
                _(
                    '%(action)s is not allowed before the minimum commitment ends on %(date)s.',
                    action=action_label,
                    date=commitment_end_date,
                )
            )
        return True

    def _prepare_subscription_quote_line_values(self, line):
        self.ensure_one()
        values = {
            'product_id': line.product_id.id,
            'name': line.name,
            'product_uom_qty': line.product_uom_qty,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'is_recurring': line.is_recurring,
        }
        if 'product_uom' in line._fields and line.product_uom:
            values['product_uom'] = line.product_uom.id
        elif 'product_uom_id' in line._fields and line.product_uom_id:
            values['product_uom_id'] = line.product_uom_id.id
        if 'tax_id' in line._fields and line.tax_id:
            values['tax_id'] = [(6, 0, line.tax_id.ids)]
        elif 'tax_ids' in line._fields and line.tax_ids:
            values['tax_ids'] = [(6, 0, line.tax_ids.ids)]
        if 'recurring_interval_count' in line._fields:
            values['recurring_interval_count'] = line.recurring_interval_count
        if 'recurring_interval_unit' in line._fields:
            values['recurring_interval_unit'] = line.recurring_interval_unit
        return values

    def _prepare_subscription_quote_values(self, quote_type):
        self.ensure_one()
        start_date = self.next_invoice_date or self.subscription_end_date or fields.Date.today()
        effective_date = start_date if quote_type == 'renewal' else fields.Date.today()
        end_date = self.subscription_plan_id.get_next_invoice_date(start_date) if self.subscription_plan_id else False
        name_prefix = _('Renewal') if quote_type == 'renewal' else _('Upsell')
        return {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'pricelist_id': self.pricelist_id.id,
            'payment_term_id': self.payment_term_id.id,
            'user_id': self.user_id.id,
            'team_id': self.team_id.id,
            'origin': self.name,
            'client_order_ref': '%s - %s' % (name_prefix, self.subscription_code or self.name),
            'is_subscription': False,
            'subscription_quote_type': quote_type,
            'subscription_origin_id': self.id,
            'subscription_plan_id': self.subscription_plan_id.id,
            'billing_interval_count': self.billing_interval_count,
            'billing_interval_unit': self.billing_interval_unit,
            'subscription_quote_effective_date': effective_date,
            'subscription_start_date': start_date,
            'subscription_end_date': end_date,
            'next_invoice_date': end_date,
        }

    def _create_subscription_quote(self, quote_type, copy_recurring_lines=False):
        self.ensure_one()
        if not self.is_subscription:
            raise UserError(_("Only subscriptions can create subscription quotations."))
        if self.subscription_state in ['cancelled', 'expired']:
            raise UserError(_("Cancelled or expired subscriptions cannot create new subscription quotations."))

        values = self._prepare_subscription_quote_values(quote_type)
        recurring_lines = self.order_line.filtered(lambda line: line.is_recurring and not line.display_type)
        if copy_recurring_lines:
            values['order_line'] = [
                (0, 0, self._prepare_subscription_quote_line_values(line))
                for line in recurring_lines
            ]
        quote = self.env['sale.order'].create(values)
        event_type = 'renewal_quote_created' if quote_type == 'renewal' else 'upsell_quote_created'
        self._log_subscription_event(
            event_type,
            _('%(quote_type)s quotation %(quote)s created', quote_type=quote.subscription_quote_type.title(), quote=quote.name),
            new_values={'quote_id': quote.id, 'quote_name': quote.name},
        )
        return quote

    def _get_subscription_quote_action(self, quote):
        self.ensure_one()
        return {
            'name': quote.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': quote.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_renew_subscription(self):
        self.ensure_one()
        quote = self._create_subscription_quote('renewal', copy_recurring_lines=True)
        return self._get_subscription_quote_action(quote)

    def action_upsell_subscription(self):
        self.ensure_one()
        quote = self._create_subscription_quote('upsell', copy_recurring_lines=False)
        return self._get_subscription_quote_action(quote)

    def action_view_subscription_sales_history(self):
        self.ensure_one()
        return {
            'name': _('Subscription Sales History'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': ['|', ('id', '=', self.id), ('subscription_origin_id', '=', self.id)],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_subscription_origin_id': self.id,
            },
        }

    def action_view_subscription_cancellation_requests(self):
        self.ensure_one()
        return {
            'name': _('Cancellation Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.cancellation.request',
            'view_mode': 'list,form,activity',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def action_view_subscription_lifecycle_requests(self):
        self.ensure_one()
        return {
            'name': _('Lifecycle Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.lifecycle.request',
            'view_mode': 'list,form,activity',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def _apply_renewal_quote(self):
        self.ensure_one()
        subscription = self.subscription_origin_id
        if not subscription:
            return False

        old_values = {
            'subscription_end_date': subscription.subscription_end_date,
            'next_invoice_date': subscription.next_invoice_date,
        }
        new_end_date = self.subscription_end_date or self.next_invoice_date
        values = {}
        if new_end_date:
            values['subscription_end_date'] = new_end_date
        if subscription.subscription_state == 'expired':
            values.update({
                'subscription_state': 'active',
                'next_invoice_date': self.subscription_start_date or fields.Date.today(),
            })
        if values:
            subscription.write(values)
        subscription._log_subscription_event(
            'renewed',
            _('Subscription renewed from quotation %s') % self.name,
            old_values=old_values,
            new_values={
                'quotation': self.name,
                'subscription_end_date': subscription.subscription_end_date,
                'next_invoice_date': subscription.next_invoice_date,
            },
        )
        return True

    def _create_upsell_proration(self, subscription, old_mrr, new_mrr):
        return False

    def _apply_upsell_quote(self):
        self.ensure_one()
        subscription = self.subscription_origin_id
        if not subscription:
            return False

        quote_lines = self.order_line.filtered(lambda line: not line.display_type and line.product_id)
        if not quote_lines:
            raise UserError(_("Add at least one product line before confirming an upsell quotation."))

        old_mrr = subscription.mrr
        subscription.write({
            'order_line': [
                (0, 0, subscription._prepare_subscription_quote_line_values(line))
                for line in quote_lines
            ],
        })
        subscription.invalidate_recordset(['recurring_total', 'mrr'])
        new_mrr = subscription.mrr
        proration = self._create_upsell_proration(subscription, old_mrr, new_mrr)
        subscription._log_subscription_event(
            'upsold',
            _('Upsell quotation %s confirmed') % self.name,
            old_values={'mrr': old_mrr},
            new_values={
                'mrr': new_mrr,
                'quotation': self.name,
                'effective_date': self.subscription_quote_effective_date,
                'proration_id': proration.id if proration else False,
            },
        )
        subscription._log_mrr_movement(
            'expansion' if new_mrr >= old_mrr else 'contraction',
            old_mrr,
            new_mrr,
            _('MRR change from upsell quotation %s') % self.name,
        )
        return True

    def action_confirm(self):
        res = super().action_confirm()
        for order in self.filtered(lambda sale: sale.subscription_origin_id and sale.subscription_quote_type):
            if order.subscription_quote_type == 'renewal':
                order._apply_renewal_quote()
            elif order.subscription_quote_type == 'upsell':
                order._apply_upsell_quote()
        return res

    def action_confirm_subscription(self):
        for order in self:
            if not order.is_subscription:
                continue
            if order.subscription_state != 'draft':
                raise UserError(_("Only draft subscriptions can be confirmed."))
            
            if not order.subscription_code:
                order.subscription_code = self.env['ir.sequence'].next_by_code('subscription.code') or 'New'
            
            plan = order.subscription_plan_id
            today = fields.Date.today()
            if plan and plan.trial_days > 0:
                order.subscription_state = 'trial'
                order.trial_start_date = today
                order.trial_end_date = today + relativedelta(days=plan.trial_days)
                order._log_subscription_event('trial_started', _('Trial started for %s days') % plan.trial_days)
            else:
                order.subscription_state = 'active'
                order.subscription_start_date = today
                order.next_invoice_date = today
                order._log_subscription_event('activated', 'Subscription activated without trial')
                order._log_mrr_movement('new', 0.0, order.mrr, 'New MRR from subscription activation')
            order.action_confirm()

    def action_trial_convert(self):
        for order in self:
            if order.subscription_state != 'trial':
                raise UserError(_("Only trial subscriptions can be converted."))
            order.subscription_state = 'active'
            order.subscription_start_date = fields.Date.today()
            order.next_invoice_date = fields.Date.today()
            order._log_subscription_event('trial_converted', 'Trial converted to active subscription')
            order._log_mrr_movement('new', 0.0, order.mrr, 'New MRR from trial conversion')

    def action_pause_subscription(self):
        for order in self:
            if order.subscription_state != 'active':
                raise UserError(_("Only active subscriptions can be paused."))
            if order.subscription_plan_id and not order.subscription_plan_id.pause_allowed:
                raise UserError(_("This subscription plan does not allow pausing."))
            
            order.subscription_state = 'paused'
            order.pause_date = fields.Date.today()
            order._log_subscription_event('paused', _('Subscription paused by user'))

    def action_resume_subscription(self):
        for order in self:
            if order.subscription_state != 'paused':
                raise UserError(_("Only paused subscriptions can be resumed."))
            today = fields.Date.today()
            pause_date = order.pause_date or today
            paused_days = max((today - pause_date).days, 0)
            if order.subscription_plan_id.max_pause_days and paused_days > order.subscription_plan_id.max_pause_days:
                raise UserError(_("This subscription has exceeded the maximum pause duration for its plan."))

            old_next_invoice_date = order.next_invoice_date
            new_next_invoice_date = old_next_invoice_date
            if old_next_invoice_date and paused_days:
                new_next_invoice_date = old_next_invoice_date + relativedelta(days=paused_days)
                if new_next_invoice_date < today:
                    new_next_invoice_date = today

            order.subscription_state = 'active'
            order.resume_date = today
            if new_next_invoice_date:
                order.next_invoice_date = new_next_invoice_date
                
            order._log_subscription_event(
                'resumed',
                _('Subscription resumed after %(days)s paused day(s)', days=paused_days),
                old_values={'next_invoice_date': old_next_invoice_date},
                new_values={'next_invoice_date': order.next_invoice_date},
            )

    def _portal_request_lifecycle_action(self, request_type, feedback, requester):
        self.ensure_one()
        requester.ensure_one()
        if request_type not in ['pause', 'resume']:
            raise ValidationError(_("Select a valid lifecycle action."))
        if not self.is_subscription:
            raise ValidationError(_("Only subscriptions can request lifecycle changes."))
        if self.subscription_state in ['cancelled', 'expired']:
            raise ValidationError(_("Cancelled or expired subscriptions cannot request lifecycle changes."))
        if 'pending_plan_change_id' in self._fields and self.pending_plan_change_id:
            raise ValidationError(_("This subscription already has a scheduled plan change."))
        if self.pending_cancellation:
            raise ValidationError(_("This subscription already has a scheduled cancellation."))

        if 'subscription.plan.change.request' in self.env.registry:
            pending_plan_change_request = self.env['subscription.plan.change.request'].search([
                ('subscription_id', '=', self.id),
                ('state', '=', 'pending'),
            ], limit=1)
            if pending_plan_change_request:
                raise ValidationError(_("This subscription already has a pending plan change request."))

        existing_request = self.env['subscription.lifecycle.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if existing_request:
            raise ValidationError(_("This subscription already has a pending lifecycle request."))

        if request_type == 'pause':
            if self.subscription_state != 'active':
                raise ValidationError(_("Only active subscriptions can request pause."))
            if self.subscription_plan_id and not self.subscription_plan_id.pause_allowed:
                raise ValidationError(_("This subscription plan does not allow pausing."))
        else:
            if self.subscription_state != 'paused':
                raise ValidationError(_("Only paused subscriptions can request resume."))
            pause_date = self.pause_date or fields.Date.today()
            paused_days = max((fields.Date.today() - pause_date).days, 0)
            if self.subscription_plan_id.max_pause_days and paused_days > self.subscription_plan_id.max_pause_days:
                raise UserError(_("This subscription has exceeded the maximum pause duration for its plan."))

        lifecycle_request = self.env['subscription.lifecycle.request'].create({
            'subscription_id': self.id,
            'request_type': request_type,
            'feedback': feedback,
            'requested_by_id': requester.id,
        })
        self._log_subscription_event(
            'lifecycle_requested',
            _('Portal %(request_type)s request %(request)s created', request_type=request_type, request=lifecycle_request.name),
            new_values={
                'request_id': lifecycle_request.id,
                'request_type': request_type,
                'requested_by': requester.display_name,
            },
        )
        return lifecycle_request

    def action_cancel_subscription(self):
        self.ensure_one()
        return {
            'name': _('Cancel Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }

    def _get_cancellation_effective_date(self, policy=None, requested_date=None):
        self.ensure_one()
        requested_date = requested_date or fields.Date.today()
        policy = policy or (self.subscription_plan_id.cancellation_policy if self.subscription_plan_id else 'immediate')
        if policy == 'end_of_period':
            effective_date = self.trial_end_date if self.subscription_state == 'trial' else self.next_invoice_date
            effective_date = effective_date or self.current_period_end or requested_date
            return max(effective_date, requested_date)
        return requested_date

    def _action_schedule_cancel(self, reason_id=None, feedback=None, effective_date=None, policy='end_of_period'):
        for order in self:
            if order.subscription_state in ['cancelled', 'expired']:
                continue
            effective_date = effective_date or order._get_cancellation_effective_date(policy)
            order._check_minimum_commitment(_('Cancellation'), effective_date=effective_date)
            if effective_date <= fields.Date.today():
                order._action_cancel(
                    reason_id=reason_id,
                    feedback=feedback,
                    cancellation_date=effective_date,
                    cancellation_policy=policy,
                )
                continue

            order.write({
                'pending_cancellation': True,
                'cancellation_requested_date': fields.Date.today(),
                'cancellation_effective_date': effective_date,
                'cancellation_policy_applied': policy,
                'cancellation_reason_id': reason_id or False,
                'cancellation_feedback': feedback or False,
            })
            order._log_subscription_event(
                'cancellation_scheduled',
                _('Subscription cancellation scheduled for %s') % effective_date,
                new_values={'cancellation_effective_date': effective_date, 'policy': policy},
            )

    def _portal_request_cancellation(self, reason, feedback, requester):
        self.ensure_one()
        reason.ensure_one()
        requester.ensure_one()

        if not self.is_subscription:
            raise ValidationError(_("Only subscriptions can request cancellation."))
        if self.subscription_state not in ['active', 'trial', 'paused', 'past_due']:
            raise ValidationError(_("Only active, trial, paused, or past-due subscriptions can request cancellation."))
        if 'pending_plan_change_id' in self._fields and self.pending_plan_change_id:
            raise ValidationError(_("This subscription already has a scheduled plan change."))
        if self.pending_cancellation:
            raise ValidationError(_("This subscription already has a scheduled cancellation."))
        if 'subscription.plan.change.request' in self.env.registry:
            pending_plan_change_request = self.env['subscription.plan.change.request'].search([
                ('subscription_id', '=', self.id),
                ('state', '=', 'pending'),
            ], limit=1)
            if pending_plan_change_request:
                raise ValidationError(_("This subscription already has a pending plan change request."))
        pending_lifecycle_request = self.env['subscription.lifecycle.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if pending_lifecycle_request:
            raise ValidationError(_("This subscription already has a pending lifecycle request."))

        existing_request = self.env['subscription.cancellation.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if existing_request:
            raise ValidationError(_("This subscription already has a pending cancellation request."))

        policy = self.subscription_plan_id.cancellation_policy if self.subscription_plan_id else 'immediate'
        effective_date = self._get_cancellation_effective_date(policy=policy)
        self._check_minimum_commitment(_('Cancellation'), effective_date=effective_date)
        request = self.env['subscription.cancellation.request'].create({
            'subscription_id': self.id,
            'reason_id': reason.id,
            'feedback': feedback,
            'requested_effective_date': effective_date,
            'requested_policy': policy,
            'requested_by_id': requester.id,
        })
        self._log_subscription_event(
            'cancellation_requested',
            _('Portal cancellation request %(request)s created', request=request.name),
            new_values={
                'request_id': request.id,
                'reason': reason.display_name,
                'effective_date': effective_date,
                'policy': policy,
                'requested_by': requester.display_name,
            },
        )
        return request

    def action_reverse_scheduled_cancellation(self):
        for order in self:
            if not order.pending_cancellation:
                continue
            old_values = {
                'cancellation_effective_date': order.cancellation_effective_date,
                'cancellation_reason_id': order.cancellation_reason_id.display_name,
            }
            order.write({
                'pending_cancellation': False,
                'cancellation_requested_date': False,
                'cancellation_effective_date': False,
                'cancellation_policy_applied': False,
                'cancellation_reason_id': False,
                'cancellation_feedback': False,
            })
            order._log_subscription_event(
                'cancellation_reversed',
                _('Scheduled cancellation reversed'),
                old_values=old_values,
            )

    def _action_cancel(self, reason_id=None, feedback=None, cancellation_date=None, cancellation_policy='immediate'):
        for order in self:
            if order.subscription_state in ['cancelled', 'expired']:
                continue
            order._check_minimum_commitment(_('Cancellation'), effective_date=cancellation_date or fields.Date.today())

            previous_mrr = order.mrr if order.subscription_state in ['active', 'paused', 'past_due'] else 0.0
            
            order.subscription_state = 'cancelled'
            order.cancellation_date = cancellation_date or fields.Date.today()
            order.cancellation_effective_date = order.cancellation_date
            order.cancellation_policy_applied = cancellation_policy
            order.pending_cancellation = False
            if reason_id:
                order.cancellation_reason_id = reason_id
            if feedback:
                order.cancellation_feedback = feedback
                
            order._log_subscription_event('cancelled', _('Subscription cancelled'))
            order._log_mrr_movement('churn', previous_mrr, 0.0, 'Churned MRR from subscription cancellation')

    def action_expire_subscription(self):
        for order in self:
            if order.subscription_state == 'active':
                previous_mrr = order.mrr
                order.subscription_state = 'expired'
                order._log_subscription_event('expired', 'Subscription expired')
                order._log_mrr_movement('churn', previous_mrr, 0.0, 'Churned MRR from subscription expiry')

    @api.model
    def _cron_generate_subscription_invoices(self):
        today = fields.Date.today()
        subscriptions = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'active'),
            ('next_invoice_date', '<=', today),
        ])
        
        batch_size = int(self.env['ir.config_parameter'].sudo().get_param('subscription_suite.batch_size', 50))
        for i in range(0, len(subscriptions), batch_size):
            batch = subscriptions[i:i + batch_size]
            for sub in batch:
                try:
                    with self.env.cr.savepoint():
                        sub._generate_subscription_invoice()
                except Exception as e:
                    _logger.error(
                        'Failed to generate invoice for subscription %s: %s',
                        sub.subscription_code, str(e)
                    )

    def _generate_subscription_invoice(self):
        self.ensure_one()
        # Create invoice from order lines
        invoices = self._create_invoices()
        invoice = invoices[:1]
        if invoice:
            invoice.subscription_id = self.id
            self.last_invoice_date = fields.Date.today()
            
            if self.subscription_plan_id:
                self.next_invoice_date = self.subscription_plan_id.get_next_invoice_date(self.last_invoice_date)
            else:
                # Fallback if no plan
                interval = self.billing_interval_count or 1
                unit = self.billing_interval_unit or 'month'
                if unit == 'day':
                    self.next_invoice_date = self.last_invoice_date + relativedelta(days=interval)
                elif unit == 'week':
                    self.next_invoice_date = self.last_invoice_date + relativedelta(weeks=interval)
                elif unit == 'month':
                    self.next_invoice_date = self.last_invoice_date + relativedelta(months=interval)
                elif unit == 'year':
                    self.next_invoice_date = self.last_invoice_date + relativedelta(years=interval)
            
            self._log_subscription_event('invoice_generated', _('Generated invoice %s') % invoice.name)
            return invoice
        return False

    @api.model
    def _cron_check_trial_expiry(self):
        today = fields.Date.today()
        trials_to_expire = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'trial'),
            ('trial_end_date', '<', today),
        ])
        for sub in trials_to_expire:
            sub.subscription_state = 'expired'
            sub._log_subscription_event('trial_expired', 'Trial expired without conversion')

    @api.model
    def _cron_check_subscription_expiry(self):
        today = fields.Date.today()
        subs_to_expire = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ['active', 'paused', 'past_due']),
            ('subscription_end_date', '!=', False),
            ('subscription_end_date', '<=', today),
        ])
        for sub in subs_to_expire:
            sub.action_expire_subscription()

    @api.model
    def _cron_process_scheduled_cancellations(self):
        today = fields.Date.today()
        subscriptions = self.search([
            ('is_subscription', '=', True),
            ('pending_cancellation', '=', True),
            ('cancellation_effective_date', '<=', today),
            ('subscription_state', 'not in', ['cancelled', 'expired']),
        ])
        for subscription in subscriptions:
            subscription._action_cancel(
                reason_id=subscription.cancellation_reason_id.id,
                feedback=subscription.cancellation_feedback,
                cancellation_date=subscription.cancellation_effective_date,
                cancellation_policy=subscription.cancellation_policy_applied or 'end_of_period',
            )
