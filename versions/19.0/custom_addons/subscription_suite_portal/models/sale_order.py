from odoo import _, api, fields, models
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _create_portal_recovery_demo_data(self):
        """Create repeatable portal payment recovery demo records."""
        partner_saved = self._get_or_create_demo_partner(
            'Subscription Portal Recovery - Saved Method',
            'portal.recovery.saved@example.com',
        )
        partner_no_method = self._get_or_create_demo_partner(
            'Subscription Portal Recovery - No Method',
            'portal.recovery.nomethod@example.com',
        )
        partner_clear = self._get_or_create_demo_partner(
            'Subscription Portal Recovery - Clear',
            'portal.recovery.clear@example.com',
        )
        partner_other = self._get_or_create_demo_partner(
            'Subscription Portal Recovery - Other Customer',
            'portal.recovery.other@example.com',
        )

        for partner in (partner_saved, partner_no_method, partner_clear, partner_other):
            self._get_or_create_demo_portal_user(partner)

        token = self._get_or_create_demo_payment_token(partner_saved)
        backup_token = self._get_or_create_demo_payment_token(
            partner_saved,
            provider_ref='portal-recovery-demo-backup-token',
            payment_details='1881',
        )
        self._get_or_create_recovery_subscription(
            partner_saved,
            'PORTAL-RECOVERY-SAVED',
            _('Portal Recovery Demo - Saved Method'),
            token=token,
            backup_token=backup_token,
            create_invoice=True,
            state='past_due',
        )
        self._get_or_create_recovery_subscription(
            partner_no_method,
            'PORTAL-RECOVERY-NOMETHOD',
            _('Portal Recovery Demo - No Saved Method'),
            create_invoice=True,
            state='past_due',
        )
        self._get_or_create_recovery_subscription(
            partner_clear,
            'PORTAL-RECOVERY-CLEAR',
            _('Portal Recovery Demo - No Open Invoice'),
            create_invoice=False,
            state='active',
        )
        self._get_or_create_recovery_subscription(
            partner_other,
            'PORTAL-RECOVERY-OTHER',
            _('Portal Recovery Demo - Access Isolation'),
            create_invoice=True,
            state='past_due',
        )
        return True

    @api.model
    def _get_or_create_demo_partner(self, name, email):
        partner = self.env['res.partner'].search([('email', '=', email)], limit=1)
        if partner:
            return partner
        return self.env['res.partner'].create({
            'name': name,
            'email': email,
        })

    @api.model
    def _get_or_create_demo_portal_user(self, partner):
        user = self.env['res.users'].search([('login', '=', partner.email)], limit=1)
        if user:
            return user
        return self.env['res.users'].create({
            'name': partner.name,
            'login': partner.email,
            'password': 'portal',
            'partner_id': partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

    @api.model
    def _get_or_create_demo_payment_token(self, partner, provider_ref='portal-recovery-demo-token', payment_details='4242'):
        token = self.env['payment.token'].sudo().search([
            ('provider_ref', '=', provider_ref),
            ('partner_id', '=', partner.id),
        ], limit=1)
        if token:
            return token

        provider = self._get_or_create_demo_payment_provider()
        payment_method = provider.payment_method_ids[:1]
        return self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'payment_details': payment_details,
            'partner_id': partner.id,
            'provider_ref': provider_ref,
            'active': True,
        })

    @api.model
    def _get_or_create_demo_payment_provider(self):
        provider = self.env['payment.provider'].sudo().search([
            ('name', '=', 'Portal Recovery Demo Provider'),
        ], limit=1)
        if provider:
            return provider

        payment_method = self.env.ref('payment.payment_method_unknown')
        redirect_form = self.env['ir.ui.view'].create({
            'name': 'Portal Recovery Demo Redirect Form',
            'type': 'qweb',
            'arch': '<form action="dummy" method="post"/>',
        })
        provider = self.env['payment.provider'].sudo().create({
            'name': 'Portal Recovery Demo Provider',
            'code': 'none',
            'state': 'test',
            'is_published': True,
            'allow_tokenization': True,
            'payment_method_ids': [Command.set([payment_method.id])],
            'redirect_form_view_id': redirect_form.id,
            'available_currency_ids': [Command.set([self.env.company.currency_id.id])],
        })
        payment_method.write({
            'active': True,
            'support_tokenization': True,
        })
        return provider

    @api.model
    def _get_or_create_recovery_subscription(self, partner, client_ref, name, token=None, backup_token=None, create_invoice=False, state='active'):
        subscription = self.search([('client_order_ref', '=', client_ref)], limit=1)
        if not subscription:
            product = self.env.ref('subscription_suite.demo_product_basic')
            plan = self.env.ref('subscription_suite.demo_plan_basic')
            subscription = self.create({
                'partner_id': partner.id,
                'client_order_ref': client_ref,
                'is_subscription': True,
                'subscription_plan_id': plan.id,
                'billing_interval_count': 1,
                'billing_interval_unit': 'month',
                'subscription_state': 'draft',
                'subscription_start_date': fields.Date.today(),
                'next_invoice_date': fields.Date.today(),
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'name': name,
                    'product_uom_qty': 1.0,
                    'price_unit': product.list_price,
                    'is_recurring': True,
                })],
            })
            subscription.action_confirm()
        subscription.write({
            'subscription_state': state,
            'payment_token_id': token.id if token else False,
            'backup_payment_token_id': backup_token.id if backup_token else False,
        })
        if create_invoice and not subscription._get_payment_recovery_invoices():
            invoice = subscription._create_invoices()[:1]
            invoice.write({
                'subscription_id': subscription.id,
                'invoice_date_due': fields.Date.today(),
            })
            invoice.action_post()
        return subscription
