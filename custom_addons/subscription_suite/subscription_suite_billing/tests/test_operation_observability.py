from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSubscriptionOperationObservability(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Run = self.env['subscription.operation.run']
        self.company = self.env.company
        self.other_company = self.env['res.company'].create({'name': 'Observability Other Company'})
        self.user = self._create_user(
            'operation-user@example.com',
            self.env.ref('subscription_suite.group_subscription_user'),
            [self.company],
        )
        self.manager = self._create_user(
            'operation-manager@example.com',
            self.env.ref('subscription_suite.group_subscription_manager'),
            [self.company, self.other_company],
        )
        self.accountant = self._create_user(
            'operation-accountant@example.com',
            self.env.ref('account.group_account_readonly'),
            [self.company],
        )

    def _create_user(self, login, group, companies):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login,
            'login': login,
            'email': login,
            'company_id': companies[0].id,
            'company_ids': [Command.set([company.id for company in companies])],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                group.id,
            ])],
        })

    def test_run_outcome_states_and_counts(self):
        success = self.Run._start_run('recurring_billing')
        success._finish_run(processed=2, succeeded=2)
        partial = self.Run._start_run('billing_retry')
        partial._finish_run(processed=2, succeeded=1, failed=1, errors=['one failed'])
        failed = self.Run._start_run('payment_collection')
        failed._finish_run(processed=1, failed=1, errors=['provider failed'])
        skipped = self.Run._start_run('mrr_snapshot')
        skipped._finish_run()

        self.assertEqual(success.state, 'success')
        self.assertEqual(partial.state, 'partial')
        self.assertEqual(partial.error_summary, 'one failed')
        self.assertEqual(failed.state, 'failed')
        self.assertEqual(skipped.state, 'skipped')
        self.assertGreaterEqual(success.duration_seconds, 0.0)

    def test_operation_runs_are_company_scoped_and_read_only(self):
        own_run = self.Run._start_run('recurring_billing', company=self.company)
        other_run = self.Run._start_run('recurring_billing', company=self.other_company)

        visible = self.Run.with_user(self.user).search([])
        self.assertIn(own_run, visible)
        self.assertNotIn(other_run, visible)
        self.assertEqual(self.Run.with_user(self.accountant).browse(own_run.id).name, own_run.name)
        with self.assertRaises(AccessError):
            self.Run.with_user(self.user).create({
                'name': 'Forbidden',
                'operation_type': 'recurring_billing',
                'company_id': self.company.id,
            })
        with self.assertRaises(AccessError):
            own_run.with_user(self.accountant).write({'error_summary': 'forbidden'})

    def test_cleanup_removes_only_old_success_and_skipped_runs(self):
        old_date = fields.Datetime.now() - timedelta(days=30)
        self.company.write({
            'subscription_operation_cleanup_enabled': True,
            'subscription_operation_retention_days': 7,
        })
        success = self.Run.create({
            'name': 'Old success',
            'operation_type': 'recurring_billing',
            'company_id': self.company.id,
            'state': 'success',
            'finished_at': old_date,
        })
        skipped = self.Run.create({
            'name': 'Old skipped',
            'operation_type': 'mrr_snapshot',
            'company_id': self.company.id,
            'state': 'skipped',
            'finished_at': old_date,
        })
        failed = self.Run.create({
            'name': 'Old failed',
            'operation_type': 'payment_collection',
            'company_id': self.company.id,
            'state': 'failed',
            'finished_at': old_date,
        })
        partial = self.Run.create({
            'name': 'Old partial',
            'operation_type': 'dunning',
            'company_id': self.company.id,
            'state': 'partial',
            'finished_at': old_date,
        })

        removed = self.Run._cron_cleanup_operation_runs()

        self.assertEqual(removed, 2)
        self.assertFalse(success.exists())
        self.assertFalse(skipped.exists())
        self.assertTrue(failed.exists())
        self.assertTrue(partial.exists())

    def test_digest_is_opt_in_and_suppresses_empty_messages(self):
        self.company.write({
            'subscription_operation_digest_enabled': True,
            'subscription_operation_digest_recipient_ids': [Command.set(self.manager.ids)],
        })
        mail_count = self.env['mail.mail'].search_count([])
        self.Run._cron_send_daily_digest()
        self.assertEqual(self.env['mail.mail'].search_count([]), mail_count)

        yesterday = fields.Datetime.now() - timedelta(days=1)
        self.Run.create({
            'name': 'Yesterday failure',
            'operation_type': 'recurring_billing',
            'company_id': self.company.id,
            'state': 'failed',
            'started_at': yesterday,
            'finished_at': yesterday,
            'failed_count': 1,
        })
        mails = self.Run._cron_send_daily_digest()

        self.assertEqual(len(mails), 1)
        self.assertIn(self.manager.email, mails.email_to)
        self.assertIn('Failed or partial runs: 1', mails.body_html)

    def test_non_manager_cannot_run_manual_cleanup(self):
        with self.assertRaises(AccessError):
            self.Run.with_user(self.user).action_cleanup_operation_runs()

    def test_manager_can_review_failure_and_non_manager_cannot(self):
        run = self.Run._start_run('recurring_billing')
        run._finish_run(processed=1, failed=1, errors=['failed'])

        with self.assertRaises(AccessError):
            run.with_user(self.user).action_mark_reviewed()
        run.with_user(self.manager).action_mark_reviewed()
        self.assertTrue(run.reviewed)
        self.assertEqual(run.reviewed_by_id, self.manager)
        run.with_user(self.manager).action_reopen_review()
        self.assertFalse(run.reviewed)
