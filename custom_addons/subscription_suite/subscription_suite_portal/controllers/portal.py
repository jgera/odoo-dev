from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

class SubscriptionPortal(CustomerPortal):

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

        values = {
            'sale_order': subscription_sudo,
            'subscription': subscription_sudo,
            'invoices': invoices,
            'page_name': 'subscription',
        }
        values = self._get_page_view_values(subscription_sudo, access_token, values, 'my_subscriptions_history', False, **kw)

        return request.render("subscription_suite_portal.portal_subscription_page", values)
