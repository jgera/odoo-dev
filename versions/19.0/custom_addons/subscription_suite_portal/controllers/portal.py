from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from urllib.parse import urlencode

class SubscriptionPortal(CustomerPortal):

    def _redirect_to_subscription(self, subscription_id, **params):
        url = '/my/subscription/%s' % subscription_id
        clean_params = {key: value for key, value in params.items() if value}
        if clean_params:
            url = '%s?%s' % (url, urlencode(clean_params))
        return request.redirect(url)

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'subscription_count' in counters:
            partner = request.env.user.partner_id
            subscription_count = request.env['sale.order'].search_count([
                ('message_partner_ids', 'child_of', [partner.commercial_partner_id.id]),
                ('is_subscription', '=', True)
            ])
            values['subscription_count'] = subscription_count
        return values

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_subscriptions(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        SaleOrder = request.env['sale.order']

        domain = [
            ('message_partner_ids', 'child_of', [partner.commercial_partner_id.id]),
            ('is_subscription', '=', True)
        ]

        searchbar_sortings = {
            'date': {'label': _('Order Date'), 'order': 'date_order desc'},
            'name': {'label': _('Reference'), 'order': 'name'},
            'stage': {'label': _('Stage'), 'order': 'subscription_state'},
        }

        # default sortby order
        if not sortby:
            sortby = 'date'
        sort_order = searchbar_sortings[sortby]['order']

        # count for pager
        subscription_count = SaleOrder.search_count(domain)
        
        # pager
        pager = portal_pager(
            url="/my/subscriptions",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=subscription_count,
            page=page,
            step=self._items_per_page
        )
        
        # content
        subscriptions = SaleOrder.search(domain, order=sort_order, limit=self._items_per_page, offset=pager['offset'])
        
        values.update({
            'date': date_begin,
            'subscriptions': subscriptions,
            'page_name': 'subscription',
            'pager': pager,
            'default_url': '/my/subscriptions',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        return request.render("subscription_suite_portal.portal_my_subscriptions", values)

    @http.route(['/my/subscription/<int:subscription_id>'], type='http', auth="user", website=True)
    def portal_subscription_page(self, subscription_id, access_token=None, **kw):
        try:
            subscription_sudo = self._document_check_access('sale.order', subscription_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not subscription_sudo.is_subscription:
            return request.redirect('/my/orders/%s' % subscription_id)

        invoices = request.env['account.move'].sudo().search([
            ('subscription_id', '=', subscription_sudo.id),
            ('move_type', '=', 'out_invoice'),
        ], order='invoice_date desc, id desc')
        plan_change_requests = request.env['subscription.plan.change.request'].sudo().search([
            ('subscription_id', '=', subscription_sudo.id),
        ], order='requested_on desc, id desc')
        pending_plan_change_request = plan_change_requests.filtered(lambda plan_request: plan_request.state == 'pending')[:1]
        available_plan_change_ids = subscription_sudo.sudo()._get_portal_plan_change_options()
        cancellation_requests = request.env['subscription.cancellation.request'].sudo().search([
            ('subscription_id', '=', subscription_sudo.id),
        ], order='requested_on desc, id desc')
        pending_cancellation_request = cancellation_requests.filtered(lambda cancel_request: cancel_request.state == 'pending')[:1]
        cancellation_reason_ids = request.env['subscription.cancel.reason'].sudo().search([
            ('active', '=', True),
        ], order='sequence, id')
        lifecycle_requests = request.env['subscription.lifecycle.request'].sudo().search([
            ('subscription_id', '=', subscription_sudo.id),
        ], order='requested_on desc, id desc')
        pending_lifecycle_request = lifecycle_requests.filtered(lambda lifecycle_request: lifecycle_request.state == 'pending')[:1]

        values = {
            'sale_order': subscription_sudo,
            'subscription': subscription_sudo,
            'invoices': invoices,
            'plan_change_requests': plan_change_requests,
            'pending_plan_change_request': pending_plan_change_request,
            'available_plan_change_ids': available_plan_change_ids,
            'cancellation_requests': cancellation_requests,
            'pending_cancellation_request': pending_cancellation_request,
            'cancellation_reason_ids': cancellation_reason_ids,
            'lifecycle_requests': lifecycle_requests,
            'pending_lifecycle_request': pending_lifecycle_request,
            'plan_change_status': kw.get('plan_change_status'),
            'plan_change_error': kw.get('plan_change_error'),
            'cancellation_status': kw.get('cancellation_status'),
            'cancellation_error': kw.get('cancellation_error'),
            'lifecycle_status': kw.get('lifecycle_status'),
            'lifecycle_error': kw.get('lifecycle_error'),
            'page_name': 'subscription',
        }
        values = self._get_page_view_values(subscription_sudo, access_token, values, 'my_subscriptions_history', False, **kw)

        return request.render("subscription_suite_portal.portal_subscription_page", values)

    @http.route(
        ['/my/subscription/<int:subscription_id>/plan-change/request'],
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
    )
    def portal_subscription_request_plan_change(self, subscription_id, new_plan_id=None, **kw):
        try:
            subscription_sudo = self._document_check_access('sale.order', subscription_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        try:
            try:
                plan_id = int(new_plan_id or 0)
            except (TypeError, ValueError):
                plan_id = 0
            new_plan = request.env['subscription.plan'].sudo().browse(plan_id).exists()
            if not new_plan:
                raise ValidationError(_('Select an allowed plan change option.'))
            subscription_sudo.sudo()._portal_request_plan_change(new_plan, request.env.user)
        except (UserError, ValidationError) as error:
            return self._redirect_to_subscription(subscription_sudo.id, plan_change_error=error.args[0])

        return self._redirect_to_subscription(subscription_sudo.id, plan_change_status='requested')

    @http.route(
        ['/my/subscription/<int:subscription_id>/cancellation/request'],
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
    )
    def portal_subscription_request_cancellation(self, subscription_id, reason_id=None, feedback=None, **kw):
        try:
            subscription_sudo = self._document_check_access('sale.order', subscription_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        try:
            try:
                cancel_reason_id = int(reason_id or 0)
            except (TypeError, ValueError):
                cancel_reason_id = 0
            reason = request.env['subscription.cancel.reason'].sudo().browse(cancel_reason_id).exists()
            if not reason or not reason.active:
                raise ValidationError(_('Select a cancellation reason.'))
            subscription_sudo.sudo()._portal_request_cancellation(
                reason,
                feedback,
                request.env.user,
            )
        except (UserError, ValidationError) as error:
            return self._redirect_to_subscription(subscription_sudo.id, cancellation_error=error.args[0])

        return self._redirect_to_subscription(subscription_sudo.id, cancellation_status='requested')

    @http.route(
        ['/my/subscription/<int:subscription_id>/lifecycle/request'],
        type='http',
        auth='user',
        website=True,
        methods=['POST'],
    )
    def portal_subscription_request_lifecycle(self, subscription_id, request_type=None, feedback=None, **kw):
        try:
            subscription_sudo = self._document_check_access('sale.order', subscription_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        try:
            subscription_sudo.sudo()._portal_request_lifecycle_action(
                request_type,
                feedback,
                request.env.user,
            )
        except (UserError, ValidationError) as error:
            return self._redirect_to_subscription(subscription_sudo.id, lifecycle_error=error.args[0])

        return self._redirect_to_subscription(subscription_sudo.id, lifecycle_status='requested')
