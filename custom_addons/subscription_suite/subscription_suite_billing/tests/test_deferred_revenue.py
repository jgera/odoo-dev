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
            'invoice_date': period_start or self.period_start,
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

    def _create_posted_credit_note(self, invoice, amount, period_start=False, period_end=False):
        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': invoice.partner_id.id,
            'subscription_id': invoice.subscription_id.id,
            'reversed_entry_id': invoice.id,
            'invoice_date': period_start or invoice.subscription_period_start,
            'subscription_period_start': period_start or invoice.subscription_period_start,
            'subscription_period_end': period_end or invoice.subscription_period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Deferred Revenue Credit Note',
                'quantity': 1.0,
                'price_unit': amount,
            })],
        })
        credit_note.action_post()
        return credit_note

    def _generate_reconciliation(self, opening_date=False, closing_date=False, plan=False):
        return self.env['subscription.deferred.revenue.reconciliation'].generate_reconciliation(
            opening_date or self.period_start,
            closing_date or self.period_end,
            company=self.env.company,
            plan=plan,
        )

    def _post_recognition_line(self, schedule, line=False, amount=False):
        line = line or schedule.line_ids.sorted('period_start')[0]
        amount = amount if amount is not False else line.amount
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': line.period_end,
            'journal_id': self.recognition_journal.id,
            'company_id': schedule.company_id.id,
            'ref': 'Test revenue recognition',
            'line_ids': [
                (0, 0, {
                    'name': 'Test revenue recognition',
                    'account_id': self.deferred_account.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': amount,
                }),
                (0, 0, {
                    'name': 'Test revenue recognition',
                    'account_id': self.revenue_account.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': -amount,
                }),
            ],
        })
        move.action_post()
        line.with_context(deferred_revenue_internal_write=True).write({
            'state': 'recognized',
            'recognized_date': line.period_end,
            'recognition_move_id': move.id,
        })
        return move

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

    def test_credit_note_adjustment_cancels_unrecognized_draft_lines(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        first_line = schedule.line_ids.sorted('period_start')[0]
        credit_note = self._create_posted_credit_note(
            invoice,
            first_line.amount,
            period_start=first_line.period_start,
            period_end=first_line.period_end,
        )

        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        self.assertEqual(adjustment.state, 'applied')
        self.assertEqual(adjustment.schedule_id, schedule)
        self.assertEqual(adjustment.credit_note_id, credit_note)
        self.assertEqual(adjustment.adjusted_line_ids, first_line)
        self.assertEqual(first_line.state, 'cancelled')
        self.assertFalse(adjustment.reversal_move_ids)
        self.assertAlmostEqual(adjustment.draft_adjusted_amount, first_line.amount, places=2)
        self.assertAlmostEqual(adjustment.recognized_reversal_amount, 0.0, places=2)

    def test_credit_note_adjustment_reverses_recognized_lines(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        first_line = schedule.line_ids.sorted('period_start')[0]
        post_wizard = self.env['subscription.deferred.revenue.post.wizard'].create({
            'cutoff_date': first_line.period_end,
            'posting_date': first_line.period_end,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })
        post_wizard.action_post_recognition()
        recognition_move = first_line.recognition_move_id
        credit_note = self._create_posted_credit_note(
            invoice,
            first_line.amount,
            period_start=first_line.period_start,
            period_end=first_line.period_end,
        )

        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)
        reversal = adjustment.reversal_move_ids

        self.assertEqual(adjustment.state, 'applied')
        self.assertEqual(first_line.state, 'recognized')
        self.assertEqual(reversal.state, 'posted')
        self.assertEqual(reversal.reversed_entry_id, recognition_move)
        self.assertAlmostEqual(sum(reversal.line_ids.mapped('debit')), first_line.amount, places=2)
        self.assertAlmostEqual(sum(reversal.line_ids.mapped('credit')), first_line.amount, places=2)
        self.assertEqual(reversal.line_ids.filtered(lambda line: line.debit).account_id, self.revenue_account)
        self.assertEqual(reversal.line_ids.filtered(lambda line: line.credit).account_id, self.deferred_account)
        self.assertAlmostEqual(adjustment.recognized_reversal_amount, first_line.amount, places=2)

    def test_credit_note_adjustment_is_idempotent(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        first_line = schedule.line_ids.sorted('period_start')[0]
        credit_note = self._create_posted_credit_note(
            invoice,
            first_line.amount,
            period_start=first_line.period_start,
            period_end=first_line.period_end,
        )

        first = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)
        second = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        self.assertEqual(first, second)
        self.assertEqual(
            self.env['subscription.deferred.revenue.adjustment'].search_count([('credit_note_id', '=', credit_note.id)]),
            1,
        )
        self.assertEqual(first_line.state, 'cancelled')

    def test_credit_note_adjustment_blocks_over_adjustment(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        credit_note = self._create_posted_credit_note(invoice, schedule.amount_total + 1.0)

        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        self.assertEqual(adjustment.state, 'blocked')
        self.assertIn('exceeds', adjustment.block_reason)
        self.assertFalse(schedule.line_ids.filtered(lambda line: line.state == 'cancelled'))

    def test_ambiguous_credit_note_adjustment_is_blocked(self):
        _subscription, _invoice = self._create_posted_subscription_invoice()
        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Unlinked credit note',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        credit_note.action_post()

        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        self.assertEqual(adjustment.state, 'blocked')
        self.assertIn('original subscription invoice', adjustment.block_reason)

    def test_credit_note_adjustment_blocks_cancelled_schedule(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        schedule.action_cancel()
        credit_note = self._create_posted_credit_note(invoice, 100.0)

        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        self.assertEqual(adjustment.state, 'blocked')
        self.assertIn('blocked or cancelled', adjustment.block_reason)

    def test_deferred_revenue_reconciliation_ready_when_sources_agree(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        line = schedule.line_ids.sorted('period_start')[0]
        move = self._post_recognition_line(schedule, line=line)

        reconciliation = self._generate_reconciliation()

        self.assertEqual(len(reconciliation), 1)
        self.assertEqual(reconciliation.status, 'ready')
        self.assertEqual(reconciliation.invoice_ids, invoice)
        self.assertEqual(reconciliation.schedule_ids, schedule)
        self.assertEqual(reconciliation.recognition_line_ids, line)
        self.assertEqual(reconciliation.recognition_move_ids, move)
        self.assertAlmostEqual(reconciliation.invoice_deferred_amount, invoice.amount_untaxed, places=2)
        self.assertAlmostEqual(reconciliation.schedule_amount, schedule.amount_total, places=2)
        self.assertAlmostEqual(reconciliation.recognized_line_amount, line.amount, places=2)
        self.assertAlmostEqual(reconciliation.posted_journal_amount, line.amount, places=2)
        self.assertAlmostEqual(reconciliation.remaining_deferred_amount, sum((schedule.line_ids - line).mapped('amount')), places=2)
        self.assertAlmostEqual(reconciliation.variance_amount, 0.0, places=2)

    def test_deferred_revenue_reconciliation_detects_journal_variance(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        line = schedule.line_ids.sorted('period_start')[0]
        self._post_recognition_line(schedule, line=line, amount=line.amount - 10.0)

        reconciliation = self._generate_reconciliation()

        self.assertEqual(reconciliation.status, 'variance')
        self.assertAlmostEqual(reconciliation.recognized_line_amount, line.amount, places=2)
        self.assertAlmostEqual(reconciliation.posted_journal_amount, line.amount - 10.0, places=2)
        self.assertAlmostEqual(abs(reconciliation.variance_amount), 10.0, places=2)

    def test_deferred_revenue_reconciliation_detects_missing_schedule(self):
        _subscription, invoice = self._create_posted_subscription_invoice()

        reconciliation = self._generate_reconciliation()

        self.assertEqual(reconciliation.status, 'missing_schedule')
        self.assertEqual(reconciliation.invoice_ids, invoice)
        self.assertFalse(reconciliation.schedule_ids)

    def test_deferred_revenue_reconciliation_detects_missing_journal_entry(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        line = schedule.line_ids.sorted('period_start')[0]
        line.with_context(deferred_revenue_internal_write=True).write({
            'state': 'recognized',
            'recognized_date': line.period_end,
        })

        reconciliation = self._generate_reconciliation()

        self.assertEqual(reconciliation.status, 'missing_journal_entry')
        self.assertEqual(reconciliation.recognition_line_ids, line)
        self.assertFalse(reconciliation.recognition_move_ids)

    def test_deferred_revenue_reconciliation_detects_blocked_schedule(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        invoice.write({
            'subscription_period_start': False,
            'subscription_period_end': False,
        })
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        reconciliation = self._generate_reconciliation()

        self.assertEqual(schedule.state, 'blocked')
        self.assertEqual(reconciliation.status, 'blocked_schedule')
        self.assertEqual(reconciliation.schedule_ids, schedule)

    def test_deferred_revenue_reconciliation_includes_credit_note_adjustments(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        line = schedule.line_ids.sorted('period_start')[0]
        credit_note = self._create_posted_credit_note(
            invoice,
            line.amount,
            period_start=line.period_start,
            period_end=line.period_end,
        )
        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        reconciliation = self._generate_reconciliation()

        self.assertEqual(reconciliation.status, 'ready')
        self.assertEqual(reconciliation.adjustment_ids, adjustment)
        self.assertEqual(reconciliation.credit_note_ids, credit_note)
        self.assertAlmostEqual(reconciliation.credit_note_adjustment_amount, adjustment.amount_total, places=2)
        self.assertAlmostEqual(reconciliation.remaining_deferred_amount, sum(schedule.line_ids.filtered(lambda rec: rec.state == 'draft').mapped('amount')), places=2)
        self.assertAlmostEqual(reconciliation.variance_amount, 0.0, places=2)

    def test_deferred_revenue_reconciliation_handles_recognized_reversal_and_remaining_draft(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )
        line = schedule.line_ids.sorted('period_start')[0]
        post_wizard = self.env['subscription.deferred.revenue.post.wizard'].create({
            'cutoff_date': line.period_end,
            'posting_date': line.period_end,
            'schedule_id': schedule.id,
            'recognition_journal_id': self.recognition_journal.id,
            'deferred_revenue_account_id': self.deferred_account.id,
            'revenue_account_id': self.revenue_account.id,
        })
        post_wizard.action_post_recognition()
        credit_note = self._create_posted_credit_note(
            invoice,
            line.amount,
            period_start=line.period_start,
            period_end=line.period_end,
        )
        adjustment = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_note)

        reconciliation = self._generate_reconciliation()

        self.assertEqual(adjustment.state, 'applied')
        self.assertTrue(adjustment.reversal_move_ids)
        self.assertEqual(reconciliation.status, 'ready')
        self.assertEqual(reconciliation.adjustment_ids, adjustment)
        self.assertEqual(reconciliation.recognition_line_ids, line)
        self.assertEqual(reconciliation.recognition_move_ids, line.recognition_move_id)
        self.assertAlmostEqual(reconciliation.credit_note_adjustment_amount, line.amount, places=2)
        self.assertAlmostEqual(reconciliation.remaining_deferred_amount, sum(schedule.line_ids.filtered(lambda rec: rec.state == 'draft').mapped('amount')), places=2)
        self.assertAlmostEqual(reconciliation.variance_amount, 0.0, places=2)

    def test_deferred_revenue_reconciliation_separates_and_filters_plans(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        other_plan = self.env['subscription.plan'].create({
            'name': 'Deferred Revenue Other Annual',
            'code': 'DEFERRED-OTHER',
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 600.0,
                'description': 'Deferred Revenue Product',
            })],
        })
        self.plan = other_plan
        _other_subscription, other_invoice = self._create_posted_subscription_invoice(amount=600.0)
        other_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(other_invoice)

        all_rows = self._generate_reconciliation()
        self.assertEqual(set(all_rows.mapped('schedule_ids').ids), set((schedule | other_schedule).ids))

        filtered_rows = self._generate_reconciliation(plan=other_plan)

        self.assertEqual(filtered_rows.subscription_plan_id, other_plan)
        self.assertEqual(filtered_rows.schedule_ids, other_schedule)
        self.assertNotIn(schedule, filtered_rows.schedule_ids)
        self.assertIn(('id', 'in', other_schedule.ids), filtered_rows.action_view_schedules()['domain'])

    def test_deferred_revenue_reconciliation_rerun_is_idempotent(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        first = self._generate_reconciliation()
        second = self._generate_reconciliation()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(
            self.env['subscription.deferred.revenue.reconciliation'].search_count([
                ('opening_date', '=', self.period_start),
                ('closing_date', '=', self.period_end),
            ]),
            1,
        )

    def test_non_manager_cannot_generate_deferred_revenue_reconciliation(self):
        public_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            public_env['subscription.deferred.revenue.reconciliation'].generate_reconciliation(
                self.period_start,
                self.period_end,
                company=self.env.company,
            )
        with self.assertRaises(AccessError):
            public_env['subscription.deferred.revenue.reconciliation.wizard'].create({
                'opening_date': self.period_start,
                'closing_date': self.period_end,
            })
