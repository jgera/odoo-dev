from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionDeferredRevenue(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Deferred Revenue Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Deferred Revenue Product',
            'type': 'service',
            'list_price': 1200.0,
            'invoice_policy': 'order',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Deferred Revenue Annual',
            'code': 'DEFERRED-ANNUAL',
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 1200.0,
                'description': 'Deferred Revenue Product',
            })],
        })
        self.period_start = date(2026, 1, 1)
        self.period_end = date(2026, 4, 1)
        self.deferred_account = self.env['account.account'].search(
            [('account_type', 'in', ('liability_current', 'liability_non_current'))],
            limit=1,
        ) or self.env['account.account'].search([('account_type', '!=', 'off_balance')], limit=1)
        self.revenue_account = self.env['account.account'].search(
            [('account_type', '=', 'income')],
            limit=1,
        ) or self.deferred_account
        self.recognition_journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        self.config = self.env['ir.config_parameter'].sudo()
        self._set_recognition_config()

    def _set_recognition_config(self):
        self.config.set_param('subscription_suite.deferred_revenue_account_id', self.deferred_account.id)
        self.config.set_param('subscription_suite.revenue_account_id', self.revenue_account.id)
        self.config.set_param('subscription_suite.recognition_journal_id', self.recognition_journal.id)

    def _clear_recognition_config(self):
        self.config.set_param('subscription_suite.deferred_revenue_account_id', '')
        self.config.set_param('subscription_suite.revenue_account_id', '')
        self.config.set_param('subscription_suite.recognition_journal_id', '')

    def _create_subscription(self, amount=1200.0, period_start=False, period_end=False):
        period_start = period_start or self.period_start
        period_end = period_end or self.period_end
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'subscription_start_date': period_start,
            'last_invoice_date': period_start,
            'next_invoice_date': period_end,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Deferred Revenue Product',
                'product_uom_qty': 1.0,
                'price_unit': amount,
                'is_recurring': True,
            })],
        })
        subscription.action_confirm()
        return subscription

    def _create_posted_subscription_invoice(self, amount=1200.0, period_start=False, period_end=False):
        subscription = self._create_subscription(
            amount=amount,
            period_start=period_start,
            period_end=period_end,
        )
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': period_start or self.period_start,
            'subscription_period_end': period_end or self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Deferred Revenue Product',
                'quantity': 1.0,
                'price_unit': amount,
            })],
        })
        invoice.action_post()
        return subscription, invoice

    def test_posted_subscription_invoice_creates_ready_schedule(self):
        subscription, invoice = self._create_posted_subscription_invoice()

        schedules = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        schedule = schedules[:1]

        self.assertEqual(schedule.state, 'ready', schedule.block_reason)
        self.assertEqual(schedule.subscription_id, subscription)
        self.assertEqual(schedule.invoice_id, invoice)
        self.assertEqual(schedule.service_period_start, self.period_start)
        self.assertEqual(schedule.service_period_end, self.period_end)
        self.assertAlmostEqual(schedule.amount_total, invoice.amount_untaxed, places=2)
        self.assertEqual(len(schedule.line_ids), 3, schedule.block_reason)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), invoice.amount_untaxed, places=2)

    def test_rerun_updates_existing_schedule_without_duplicates(self):
        _subscription, invoice = self._create_posted_subscription_invoice()

        first = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        second = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )

        self.assertEqual(first, second)
        self.assertEqual(
            self.env['subscription.deferred.revenue'].search_count([('invoice_id', '=', invoice.id)]),
            1,
        )
        self.assertEqual(second.recognition_method, 'equal_monthly')
        self.assertEqual(len(second.line_ids), 3)

    def test_straight_line_daily_allocation_reconciles_with_rounding(self):
        _subscription, invoice = self._create_posted_subscription_invoice(
            amount=1000.0,
            period_start=date(2026, 1, 15),
            period_end=date(2026, 4, 1),
        )

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='straight_line_daily',
        )

        self.assertEqual(len(schedule.line_ids), 3, schedule.block_reason)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), invoice.amount_untaxed, places=2)
        self.assertAlmostEqual(schedule.line_ids[-1].amount, 1000.0 - sum(schedule.line_ids[:-1].mapped('amount')), places=2)

    def test_equal_monthly_allocation_reconciles_with_rounding(self):
        _subscription, invoice = self._create_posted_subscription_invoice(amount=1000.0)

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )

        self.assertEqual(len(schedule.line_ids), 3, schedule.block_reason)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), invoice.amount_untaxed, places=2)
        self.assertAlmostEqual(schedule.line_ids[0].amount, 333.33, places=2)
        self.assertAlmostEqual(schedule.line_ids[-1].amount, 333.34, places=2)

    def test_missing_service_period_creates_blocked_schedule(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        invoice.write({
            'subscription_period_start': False,
            'subscription_period_end': False,
        })

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        self.assertEqual(schedule.state, 'blocked')
        self.assertIn('service period', schedule.block_reason)
        self.assertFalse(schedule.line_ids)

    def test_missing_recognition_config_blocks_schedule(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        self._clear_recognition_config()

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        self.assertEqual(schedule.state, 'blocked')
        self.assertIn('configuration', schedule.block_reason)
        self.assertFalse(schedule.line_ids)

    def test_mixed_invoice_only_recognizes_subscription_lines(self):
        subscription = self._create_subscription(amount=1200.0)
        subscription_line = subscription.order_line[:1]
        one_time_product = self.env['product.product'].create({
            'name': 'One-time Implementation',
            'type': 'service',
            'list_price': 500.0,
            'invoice_policy': 'order',
        })
        subscription.write({
            'order_line': [(0, 0, {
                'product_id': one_time_product.id,
                'name': 'One-time implementation',
                'product_uom_qty': 1.0,
                'price_unit': 500.0,
                'is_recurring': False,
            })],
        })
        one_time_line = subscription.order_line.filtered(lambda line: line.product_id == one_time_product)[:1]
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'name': 'Deferred Revenue Product',
                    'quantity': 1.0,
                    'price_unit': 1200.0,
                    'sale_line_ids': [(6, 0, subscription_line.ids)],
                }),
                (0, 0, {
                    'product_id': one_time_product.id,
                    'name': 'One-time implementation',
                    'quantity': 1.0,
                    'price_unit': 500.0,
                    'sale_line_ids': [(6, 0, one_time_line.ids)],
                }),
            ],
        })
        invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.product).write({
            'sale_line_ids': [(6, 0, subscription_line.ids)],
        })
        invoice.invoice_line_ids.filtered(lambda line: line.product_id == one_time_product).write({
            'sale_line_ids': [(6, 0, one_time_line.ids)],
            'exclude_from_subscription_deferred_revenue': True,
        })
        invoice.action_post()

        eligible_lines = self.env['subscription.deferred.revenue']._eligible_invoice_lines(invoice)
        self.assertEqual(eligible_lines.mapped('name'), ['Deferred Revenue Product'])

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        self.assertEqual(schedule.state, 'ready', schedule.block_reason)
        self.assertAlmostEqual(schedule.amount_total, 1200.0, places=2)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), 1200.0, places=2)

    def test_draft_non_subscription_and_refund_sources_are_blocked_or_excluded(self):
        subscription = self._create_subscription()
        draft_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Draft subscription invoice',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(draft_invoice)
        self.assertEqual(schedule.state, 'blocked')

        plain_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Plain invoice',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        plain_invoice.action_post()
        plain_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(plain_invoice)
        self.assertFalse(plain_schedule)

        refund = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Refund',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        refund.action_post()
        refund_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(refund)
        self.assertEqual(refund_schedule.state, 'blocked')

    def test_smart_button_domains_are_scoped(self):
        subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        subscription_action = subscription.action_view_deferred_revenue_schedules()
        invoice_action = invoice.action_view_deferred_revenue_schedules()

        self.assertIn(('subscription_id', '=', subscription.id), subscription_action['domain'])
        self.assertIn(('invoice_id', '=', invoice.id), invoice_action['domain'])
        self.assertEqual(schedule.invoice_id, invoice)

    def test_non_manager_cannot_generate_schedules(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        public_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            public_env['subscription.deferred.revenue'].generate_for_invoices(invoice)

    def test_ready_schedule_lines_are_locked(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        with self.assertRaises(UserError):
            schedule.line_ids[:1].write({'amount': 1.0})
        with self.assertRaises(UserError):
            schedule.line_ids[:1].unlink()

    def test_schedule_with_recognized_line_cannot_cancel_or_regenerate(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        schedule.line_ids[:1].with_context(deferred_revenue_internal_write=True).write({'state': 'recognized'})

        with self.assertRaises(UserError):
            schedule.action_cancel()
        with self.assertRaises(UserError):
            schedule.action_regenerate_lines()

    def test_recognition_preview_includes_due_draft_lines_only(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        due_line = schedule.line_ids.sorted('period_end')[0]
        future_lines = schedule.line_ids - due_line

        wizard = self.env['subscription.deferred.revenue.preview.wizard'].create({
            'cutoff_date': due_line.period_end,
            'company_id': schedule.company_id.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })
        before_moves = self.env['account.move'].search_count([])
        before_states = {line.id: line.state for line in schedule.line_ids}

        action = wizard.action_preview()

        self.assertEqual(action['res_id'], wizard.id)
        self.assertEqual(wizard.line_ids.mapped('schedule_line_id'), due_line)
        self.assertEqual(wizard.line_ids.amount, due_line.amount)
        self.assertEqual(wizard.line_ids.debit_account_id, self.deferred_account)
        self.assertEqual(wizard.line_ids.credit_account_id, self.revenue_account)
        self.assertFalse(future_lines & wizard.line_ids.mapped('schedule_line_id'))
        self.assertEqual(self.env['account.move'].search_count([]), before_moves)
        self.assertEqual({line.id: line.state for line in schedule.line_ids}, before_states)

    def test_recognition_preview_excludes_cancelled_blocked_and_recognized_lines(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        ready_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        recognized_line = ready_schedule.line_ids.sorted('period_end')[0]
        recognized_line.with_context(deferred_revenue_internal_write=True).write({'state': 'recognized'})

        _blocked_subscription, blocked_invoice = self._create_posted_subscription_invoice()
        blocked_invoice.write({
            'subscription_period_start': False,
            'subscription_period_end': False,
        })
        blocked_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(blocked_invoice)

        _cancelled_subscription, cancelled_invoice = self._create_posted_subscription_invoice()
        cancelled_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(cancelled_invoice)
        cancelled_schedule.action_cancel()

        wizard = self.env['subscription.deferred.revenue.preview.wizard'].create({
            'cutoff_date': self.period_end,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        wizard.action_preview()

        previewed_lines = wizard.line_ids.mapped('schedule_line_id')
        self.assertNotIn(recognized_line, previewed_lines)
        self.assertFalse(blocked_schedule.line_ids & previewed_lines)
        self.assertFalse(cancelled_schedule.line_ids & previewed_lines)
        self.assertTrue((ready_schedule.line_ids - recognized_line) <= previewed_lines)

    def test_recognition_preview_validates_configuration(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        wizard = self.env['subscription.deferred.revenue.preview.wizard'].create({
            'cutoff_date': self.period_end,
            'schedule_id': schedule.id,
            'recognition_journal_id': False,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        with self.assertRaises(ValidationError):
            wizard.action_preview()

    def test_recognition_preview_filters_by_subscription_and_schedule(self):
        subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        _other_subscription, other_invoice = self._create_posted_subscription_invoice(amount=600.0)
        other_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(other_invoice)

        wizard = self.env['subscription.deferred.revenue.preview.wizard'].create({
            'cutoff_date': self.period_end,
            'company_id': schedule.company_id.id,
            'subscription_id': subscription.id,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        wizard.action_preview()

        self.assertTrue(wizard.line_ids)
        self.assertEqual(wizard.line_ids.mapped('schedule_id'), schedule)
        self.assertEqual(wizard.line_ids.mapped('subscription_id'), subscription)
        self.assertFalse(other_schedule.line_ids & wizard.line_ids.mapped('schedule_line_id'))

    def test_non_manager_cannot_create_recognition_preview(self):
        public_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            public_env['subscription.deferred.revenue.preview.wizard'].create({
                'cutoff_date': self.period_end,
            })

    def test_post_recognition_creates_posted_move_and_marks_due_lines(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        due_line = schedule.line_ids.sorted('period_end')[0]
        future_lines = schedule.line_ids - due_line

        wizard = self.env['subscription.deferred.revenue.post.wizard'].create({
            'cutoff_date': due_line.period_end,
            'posting_date': due_line.period_end,
            'company_id': schedule.company_id.id,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        action = wizard.action_post_recognition()
        move = due_line.recognition_move_id

        self.assertEqual(action['res_model'], 'account.move')
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.move_type, 'entry')
        self.assertEqual(move.journal_id, self.recognition_journal)
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), due_line.amount, places=2)
        self.assertAlmostEqual(sum(move.line_ids.mapped('credit')), due_line.amount, places=2)
        self.assertEqual(move.line_ids.filtered(lambda line: line.debit).account_id, self.deferred_account)
        self.assertEqual(move.line_ids.filtered(lambda line: line.credit).account_id, self.revenue_account)
        self.assertEqual(due_line.state, 'recognized')
        self.assertEqual(due_line.recognized_date, due_line.period_end)
        self.assertFalse(future_lines.filtered('recognition_move_id'))
        self.assertTrue(all(line.state == 'draft' for line in future_lines))
        self.assertAlmostEqual(schedule.recognized_amount, due_line.amount, places=2)
        self.assertAlmostEqual(schedule.remaining_amount, schedule.amount_total - due_line.amount, places=2)

    def test_post_recognition_rerun_excludes_already_recognized_lines(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        due_line = schedule.line_ids.sorted('period_end')[0]

        wizard = self.env['subscription.deferred.revenue.post.wizard'].create({
            'cutoff_date': due_line.period_end,
            'posting_date': due_line.period_end,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })
        wizard.action_post_recognition()
        move = due_line.recognition_move_id

        with self.assertRaises(ValidationError):
            wizard.action_post_recognition()

        self.assertEqual(due_line.recognition_move_id, move)
        self.assertEqual(schedule.line_ids.mapped('recognition_move_id'), move)

    def test_post_recognition_validates_configuration(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        wizard = self.env['subscription.deferred.revenue.post.wizard'].create({
            'cutoff_date': self.period_end,
            'schedule_id': schedule.id,
            'recognition_journal_id': False,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        with self.assertRaises(ValidationError):
            wizard.action_post_recognition()

    def test_post_recognition_filters_by_subscription_and_schedule(self):
        subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        _other_subscription, other_invoice = self._create_posted_subscription_invoice(amount=600.0)
        other_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(other_invoice)

        wizard = self.env['subscription.deferred.revenue.post.wizard'].create({
            'cutoff_date': self.period_end,
            'posting_date': self.period_end,
            'company_id': schedule.company_id.id,
            'subscription_id': subscription.id,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        wizard.action_post_recognition()

        self.assertTrue(schedule.line_ids.filtered(lambda line: line.state == 'recognized'))
        self.assertFalse(other_schedule.line_ids.filtered(lambda line: line.state == 'recognized'))
        self.assertFalse(other_schedule.line_ids.mapped('recognition_move_id'))

    def test_preview_remains_non_mutating_after_posting_slice(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        due_line = schedule.line_ids.sorted('period_end')[0]
        before_moves = self.env['account.move'].search_count([])

        wizard = self.env['subscription.deferred.revenue.preview.wizard'].create({
            'cutoff_date': due_line.period_end,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })

        wizard.action_preview()

        self.assertEqual(self.env['account.move'].search_count([]), before_moves)
        self.assertFalse(schedule.line_ids.mapped('recognition_move_id'))
        self.assertTrue(all(line.state == 'draft' for line in schedule.line_ids))

    def test_non_manager_cannot_create_recognition_posting(self):
        public_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            public_env['subscription.deferred.revenue.post.wizard'].create({
                'cutoff_date': self.period_end,
            })
