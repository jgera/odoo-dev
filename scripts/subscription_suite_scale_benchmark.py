import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import timedelta

from odoo_env import DEFAULT_VERSION, add_odoo_to_path, addons_path, get_paths


DEFAULT_PREFIX = "SS-PERF"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Opt-in Subscription Suite scale data generator and benchmark harness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--odoo-version", "--version", default=DEFAULT_VERSION)
    parser.add_argument("-d", "--database", required=True)
    parser.add_argument("-c", "--config", help="Path to odoo.conf")
    parser.add_argument("--mode", choices=["plan", "generate", "benchmark", "all"], default="plan")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--subscriptions", type=int, default=10000)
    parser.add_argument("--plans", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1900)
    parser.add_argument("--chunk-size", type=int, default=250)
    parser.add_argument("--auxiliary-count", type=int, default=250)
    parser.add_argument("--billing-batch-size", type=int, default=250)
    parser.add_argument("--dunning-batch-size", type=int, default=250)
    parser.add_argument("--output", help="Optional JSON result file")
    return parser.parse_args()


def bootstrap_odoo(args):
    paths = get_paths(args.odoo_version)
    add_odoo_to_path(paths)

    import odoo
    import odoo.service.server
    from odoo.tools import config

    config_path = args.config or paths.config
    config.parse_config([
        "-c",
        str(config_path),
        "--addons-path",
        addons_path(paths),
        "--data-dir",
        str(paths.data_dir),
        "--max-cron-threads=0",
    ])
    odoo.service.server.load_server_wide_modules()


def open_env(database):
    from odoo import api, SUPERUSER_ID
    from odoo.modules.registry import Registry

    registry = Registry(database)
    cr = registry.cursor()
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    return cr, env


class SubscriptionSuiteScaleHarness:
    def __init__(self, env, args):
        self.env = env
        self.args = args
        self.random = random.Random(args.seed)
        from odoo import fields

        self.fields = fields
        self.today = fields.Date.today()
        self.period_start = self.today - timedelta(days=30)
        self.period_end = self.today

    def print_plan(self):
        print("Subscription Suite scale benchmark plan")
        print("Database:      %s" % self.args.database)
        print("Prefix:        %s" % self.args.prefix)
        print("Subscriptions: %s" % self.args.subscriptions)
        print("Plans:         %s" % self.args.plans)
        print("Auxiliary:     %s payment/dunning/finance samples" % self.args.auxiliary_count)
        print("Mode:          %s" % self.args.mode)
        print()
        print("Run with --mode generate to create data, --mode benchmark to run jobs, or --mode all for both.")

    def _require_modules(self):
        required = [
            "subscription_suite",
            "subscription_suite_billing",
            "subscription_suite_dunning",
            "subscription_suite_reports",
        ]
        installed = set(self.env["ir.module.module"].sudo().search([
            ("name", "in", required),
            ("state", "=", "installed"),
        ]).mapped("name"))
        missing = sorted(set(required) - installed)
        if missing:
            raise SystemExit("Install required modules before running benchmark: %s" % ", ".join(missing))

    def _get_or_create_product(self):
        Product = self.env["product.product"].sudo()
        product = Product.search([("default_code", "=", "%s-SERVICE" % self.args.prefix)], limit=1)
        if product:
            return product
        return Product.create({
            "name": "%s Scale Service" % self.args.prefix,
            "default_code": "%s-SERVICE" % self.args.prefix,
            "type": "service",
            "list_price": 100.0,
            "invoice_policy": "order",
        })

    def _get_or_create_partner(self, index):
        Partner = self.env["res.partner"].sudo()
        ref = "%s-CUST-%05d" % (self.args.prefix, index)
        partner = Partner.search([("ref", "=", ref)], limit=1)
        if partner:
            return partner
        return Partner.create({
            "name": "%s Customer %05d" % (self.args.prefix, index),
            "ref": ref,
            "email": "scale-%05d@example.com" % index,
        })

    def _get_or_create_plans(self, product):
        Plan = self.env["subscription.plan"].sudo()
        dunning_policy = self._get_or_create_dunning_policy()
        plans = self.env["subscription.plan"]
        for index in range(self.args.plans):
            code = "%s-PLAN-%02d" % (self.args.prefix, index + 1)
            plan = Plan.search([("code", "=", code), ("company_id", "=", self.env.company.id)], limit=1)
            if not plan:
                plan = Plan.create({
                    "name": "%s Plan %02d" % (self.args.prefix, index + 1),
                    "code": code,
                    "billing_interval_count": 1,
                    "billing_interval_unit": "month",
                    "currency_id": self.env.company.currency_id.id,
                    "company_id": self.env.company.id,
                    "dunning_policy_id": dunning_policy.id,
                    "plan_line_ids": [(0, 0, {
                        "product_id": product.id,
                        "quantity": 1.0,
                        "price_unit": 75.0 + (index * 25.0),
                        "description": "%s recurring service" % code,
                    })],
                })
            elif not plan.dunning_policy_id:
                plan.dunning_policy_id = dunning_policy.id
            plans |= plan
        return plans

    def _get_or_create_dunning_policy(self):
        Policy = self.env["subscription.dunning.policy"].sudo()
        policy = Policy.search([("name", "=", "%s Scale Dunning" % self.args.prefix)], limit=1)
        if policy:
            return policy
        template = self.env["mail.template"].sudo().create({
            "name": "%s Scale Dunning Template" % self.args.prefix,
            "model_id": self.env.ref("sale.model_sale_order").id,
            "subject": "Scale dunning {{ object.name }}",
            "email_from": '{{ object.company_id.email or "billing@example.com" }}',
            "email_to": '{{ object.partner_id.email or "customer@example.com" }}',
            "body_html": "<p>Scale benchmark recovery notice.</p>",
        })
        policy = Policy.create({
            "name": "%s Scale Dunning" % self.args.prefix,
            "grace_period_days": 0,
            "final_action": "none",
            "final_action_delay": 5,
        })
        self.env["subscription.dunning.policy.line"].sudo().create({
            "policy_id": policy.id,
            "delay_days": 1,
            "action_type": "email",
            "email_template_id": template.id,
        })
        return policy

    def _subscription_distribution(self, index):
        bucket = index % 20
        if bucket < 11:
            return "active"
        if bucket < 13:
            return "trial"
        if bucket < 15:
            return "paused"
        if bucket < 17:
            return "past_due"
        if bucket < 19:
            return "cancelled"
        return "expired"

    def _subscription_values(self, index, partner, plan, product):
        state = self._subscription_distribution(index)
        due_for_billing = state == "active" and index % 2 == 0
        next_invoice_date = self.today if due_for_billing else self.today + timedelta(days=15 + (index % 10))
        start_date = self.period_start - timedelta(days=index % 365)
        values = {
            "partner_id": partner.id,
            "company_id": self.env.company.id,
            "currency_id": self.env.company.currency_id.id,
            "client_order_ref": "%s-SUB-%05d" % (self.args.prefix, index),
            "is_subscription": True,
            "subscription_state": state,
            "subscription_plan_id": plan.id,
            "billing_interval_count": 1,
            "billing_interval_unit": "month",
            "subscription_start_date": start_date if state != "trial" else False,
            "trial_start_date": start_date if state == "trial" else False,
            "trial_end_date": start_date + timedelta(days=14) if state == "trial" else False,
            "last_invoice_date": self.period_start,
            "next_invoice_date": next_invoice_date,
            "subscription_end_date": self.today + timedelta(days=30 + (index % 60)),
            "state": "sale" if state in ("active", "trial", "paused", "past_due") else "cancel",
            "order_line": [(0, 0, {
                "product_id": product.id,
                "name": "%s recurring service %05d" % (self.args.prefix, index),
                "product_uom_qty": 1.0 + (index % 5),
                "price_unit": 75.0 + ((index % max(self.args.plans, 1)) * 25.0),
                "is_recurring": True,
                "subscription_component_type": "base",
            })],
        }
        if state == "past_due":
            values.update({
                "dunning_start_date": self.today - timedelta(days=5 + (index % 5)),
                "next_dunning_date": self.today,
            })
        if state in ("cancelled", "expired"):
            values.update({
                "cancellation_date": self.today - timedelta(days=10 + (index % 10)),
                "cancellation_feedback": "Scale benchmark churn feedback",
            })
        if index % 23 == 0 and state in ("active", "paused", "past_due"):
            values.update({
                "pending_cancellation": True,
                "cancellation_effective_date": self.today + timedelta(days=10),
            })
        return values

    def generate_subscriptions(self):
        self._require_modules()
        product = self._get_or_create_product()
        plans = self._get_or_create_plans(product)
        SaleOrder = self.env["sale.order"].sudo()
        existing = SaleOrder.search_count([
            ("client_order_ref", "=like", "%s-SUB-%%" % self.args.prefix),
        ])
        if existing >= self.args.subscriptions:
            return {"existing": existing, "created": 0}

        created = 0
        for start in range(existing, self.args.subscriptions, self.args.chunk_size):
            end = min(start + self.args.chunk_size, self.args.subscriptions)
            values = []
            for index in range(start, end):
                partner = self._get_or_create_partner(index)
                plan = plans[index % len(plans)]
                values.append(self._subscription_values(index, partner, plan, product))
            SaleOrder.create(values)
            created += len(values)
            self.env.cr.commit()
            print("Created %s/%s subscriptions" % (existing + created, self.args.subscriptions))
        return {"existing": existing, "created": created}

    def generate_auxiliary_records(self):
        self._ensure_recognition_config()
        SaleOrder = self.env["sale.order"].sudo()
        subscriptions = SaleOrder.search([
            ("client_order_ref", "=like", "%s-SUB-%%" % self.args.prefix),
            ("subscription_state", "in", ["active", "past_due"]),
        ], limit=self.args.auxiliary_count, order="id asc")
        if not subscriptions:
            return {"payment_attempts": 0, "mrr_movements": 0, "finance_schedules": 0}

        attempts = self.env["subscription.payment.attempt"].sudo()
        movements = self.env["subscription.mrr.movement"].sudo()
        created_attempts = 0
        created_movements = 0
        created_schedules = 0
        for index, subscription in enumerate(subscriptions):
            invoice = self._get_or_create_scale_invoice(subscription, index)
            existing_attempt = attempts.search([
                ("subscription_id", "=", subscription.id),
                ("invoice_id", "=", invoice.id),
                ("source", "=", "cron"),
                ("attempt_date", ">=", self.fields.Datetime.to_datetime(self.period_start)),
            ], limit=1)
            if not existing_attempt:
                attempts.create({
                    "name": "%s scale recovery attempt %05d" % (self.args.prefix, index),
                    "subscription_id": subscription.id,
                    "invoice_id": invoice.id,
                    "source": "cron",
                    "state": "failed" if index % 3 else "pending",
                    "amount": subscription.mrr or 100.0,
                    "attempt_date": self.fields.Datetime.to_datetime(self.period_start + timedelta(days=index % 20)),
                    "recovery_required": index % 3 != 0,
                })
                created_attempts += 1

            if not movements.search([
                ("subscription_id", "=", subscription.id),
                ("movement_date", "=", self.period_end),
            ], limit=1):
                amount = subscription.mrr or 100.0
                movement_type = ["new", "expansion", "contraction", "churn"][index % 4]
                movements.create({
                    "name": "%s scale %s movement %05d" % (self.args.prefix, movement_type, index),
                    "subscription_id": subscription.id,
                    "movement_date": self.period_end,
                    "movement_type": movement_type,
                    "previous_mrr": max(amount - 10.0, 0.0),
                    "new_mrr": amount,
                    "amount": amount if movement_type in ("new", "expansion") else -amount,
                })
                created_movements += 1

            if index < min(25, self.args.auxiliary_count):
                created_schedules += self._ensure_finance_schedule(subscription)

        self.env.cr.commit()
        return {
            "payment_attempts": created_attempts,
            "mrr_movements": created_movements,
            "finance_schedules": created_schedules,
        }

    def _ensure_recognition_config(self):
        company = self.env.company
        Account = self.env["account.account"].sudo()
        Journal = self.env["account.journal"].sudo()
        deferred_account = company.subscription_deferred_revenue_account_id or Account.search([
            ("account_type", "in", ("liability_current", "liability_non_current")),
        ], limit=1)
        revenue_account = company.subscription_revenue_account_id or Account.search([
            ("account_type", "=", "income"),
        ], limit=1)
        journal = company.subscription_recognition_journal_id or Journal.search([
            ("type", "=", "general"),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", company.id),
        ], limit=1)
        values = {}
        if deferred_account:
            values["subscription_deferred_revenue_account_id"] = deferred_account.id
        if revenue_account:
            values["subscription_revenue_account_id"] = revenue_account.id
        if journal:
            values["subscription_recognition_journal_id"] = journal.id
        if values:
            values["subscription_default_recognition_method"] = company.subscription_default_recognition_method or "straight_line_daily"
            company.sudo().write(values)
            self.env.cr.commit()
        return bool(deferred_account and revenue_account and journal)

    def _get_or_create_scale_invoice(self, subscription, index):
        Move = self.env["account.move"].sudo()
        invoice = Move.search([
            ("subscription_id", "=", subscription.id),
            ("move_type", "=", "out_invoice"),
            ("invoice_date", "=", self.period_start),
            ("ref", "=", "%s-SCALE-%05d" % (self.args.prefix, index)),
        ], limit=1)
        if invoice:
            return invoice
        invoice = Move.create({
            "move_type": "out_invoice",
            "partner_id": subscription.partner_id.id,
            "company_id": subscription.company_id.id,
            "currency_id": subscription.currency_id.id,
            "subscription_id": subscription.id,
            "invoice_date": self.period_start,
            "invoice_date_due": self.period_end,
            "subscription_period_start": self.period_start,
            "subscription_period_end": self.period_end,
            "ref": "%s-SCALE-%05d" % (self.args.prefix, index),
            "invoice_line_ids": [(0, 0, {
                "product_id": subscription.order_line[:1].product_id.id,
                "name": "%s payment recovery benchmark" % self.args.prefix,
                "quantity": 1.0,
                "price_unit": subscription.mrr or 100.0,
            })],
        })
        try:
            with self.env.cr.savepoint():
                invoice.action_post()
        except Exception as error:
            print("Created draft scale invoice for %s because posting failed: %s" % (subscription.display_name, error))
        return invoice

    def _ensure_finance_schedule(self, subscription):
        Move = self.env["account.move"].sudo()
        existing_invoice = Move.search([
            ("subscription_id", "=", subscription.id),
            ("move_type", "=", "out_invoice"),
            ("invoice_date", "=", self.period_start),
            ("subscription_period_start", "=", self.period_start),
        ], limit=1)
        if existing_invoice:
            schedule = self.env["subscription.deferred.revenue"].sudo().search([
                ("invoice_id", "=", existing_invoice.id),
            ], limit=1)
            if schedule and schedule.state != "blocked":
                return 0
            self.env["subscription.deferred.revenue"].sudo().generate_for_invoices(existing_invoice)
            return 1
        try:
            invoice = Move.create({
                "move_type": "out_invoice",
                "partner_id": subscription.partner_id.id,
                "company_id": subscription.company_id.id,
                "currency_id": subscription.currency_id.id,
                "subscription_id": subscription.id,
                "invoice_date": self.period_start,
                "subscription_period_start": self.period_start,
                "subscription_period_end": self.period_end,
                "invoice_line_ids": [(0, 0, {
                    "product_id": subscription.order_line[:1].product_id.id,
                    "name": "%s deferred revenue benchmark" % self.args.prefix,
                    "quantity": 1.0,
                    "price_unit": subscription.mrr or 100.0,
                })],
            })
            invoice.action_post()
            self.env["subscription.deferred.revenue"].sudo().generate_for_invoices(invoice)
            return 1
        except Exception as error:
            self.env.cr.rollback()
            print("Skipped finance schedule for %s: %s" % (subscription.display_name, error))
            return 0

    def generate(self):
        subscription_result = self.generate_subscriptions()
        auxiliary_result = self.generate_auxiliary_records()
        return {"subscriptions": subscription_result, "auxiliary": auxiliary_result}

    def _count_subscription_scope(self):
        return self.env["sale.order"].sudo().search_count([
            ("client_order_ref", "=like", "%s-SUB-%%" % self.args.prefix),
        ])

    def _timed(self, label, func):
        start = time.perf_counter()
        result = func()
        self.env.cr.commit()
        elapsed = time.perf_counter() - start
        print("%-36s %.3fs" % (label, elapsed))
        return {"label": label, "seconds": round(elapsed, 3), "result": result}

    def benchmark(self):
        self.env["ir.config_parameter"].sudo().set_param("subscription_suite.batch_size", self.args.billing_batch_size)
        self.env["ir.config_parameter"].sudo().set_param("subscription_suite.dunning_batch_size", self.args.dunning_batch_size)
        self.env.cr.commit()

        results = []
        results.append(self._timed("billing cron", self._benchmark_billing_cron))
        results.append(self._timed("dunning cron", self._benchmark_dunning_cron))
        results.append(self._timed("recognition preview selection", self._benchmark_recognition_preview))
        results.append(self._timed("generated analytics chain", self._benchmark_analytics_chain))
        return {
            "subscription_scope_count": self._count_subscription_scope(),
            "results": results,
        }

    def _benchmark_billing_cron(self):
        before = self.env["subscription.billing.attempt"].sudo().search_count([])
        self.env["sale.order"].sudo()._cron_generate_subscription_invoices()
        after = self.env["subscription.billing.attempt"].sudo().search_count([])
        return {"new_attempts": after - before}

    def _benchmark_dunning_cron(self):
        before = self.env["subscription.dunning.attempt"].sudo().search_count([])
        self.env["sale.order"].sudo()._cron_process_dunning()
        after = self.env["subscription.dunning.attempt"].sudo().search_count([])
        return {"new_attempts": after - before}

    def _benchmark_recognition_preview(self):
        lines = self.env["subscription.deferred.revenue.line"].sudo()._get_lines_for_recognition_preview(
            self.period_end,
            company=self.env.company,
        )
        return {"eligible_lines": len(lines)}

    def _benchmark_analytics_chain(self):
        company = self.env.company
        currency = company.currency_id
        opening_date = self.period_start
        closing_date = self.period_end
        start_month = opening_date.replace(day=1)
        end_month = closing_date.replace(day=1)
        self.env["subscription.mrr.snapshot"].sudo().generate_for_date(opening_date, company=company)
        self.env["subscription.mrr.snapshot"].sudo().generate_for_date(closing_date, company=company)
        self.env["subscription.mrr.reconciliation"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.mrr.movement.anomaly"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.mrr.kpi.summary"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.mrr.kpi.dashboard"].sudo().generate_for_period(opening_date, closing_date, company, currency)
        self.env["subscription.mrr.waterfall"].sudo().generate_for_period(opening_date, closing_date, company, currency)
        self.env["subscription.retention.cohort"].sudo().generate_for_period(start_month, end_month, company=company)
        self.env["subscription.revenue.forecast"].sudo().generate_for_period(start_month, end_month, company=company)
        self.env["subscription.arpu.summary"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.ltv.summary"].sudo().generate_for_period(opening_date, closing_date, start_month, end_month, company=company)
        self.env["subscription.churn.reason.summary"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.plan.performance.summary"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.at.risk.summary"].sudo().generate_for_date(closing_date, company=company)
        self.env["subscription.payment.recovery.summary"].sudo().generate_for_period(opening_date, closing_date, company=company)
        self.env["subscription.trial.conversion.summary"].sudo().generate_for_period(opening_date, closing_date, company=company)
        return {"company": company.display_name, "currency": currency.name}


def main():
    args = parse_args()
    paths = get_paths(args.odoo_version)
    if paths.venv_python.exists():
        current_python = os.path.normcase(os.path.abspath(sys.executable))
        target_python = os.path.normcase(os.path.abspath(str(paths.venv_python)))
        if current_python != target_python:
            return subprocess.call([target_python, os.path.abspath(__file__)] + sys.argv[1:])
    if args.subscriptions <= 0:
        raise SystemExit("--subscriptions must be positive")
    if args.plans <= 0:
        raise SystemExit("--plans must be positive")
    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be positive")

    bootstrap_odoo(args)
    cr, env = open_env(args.database)
    try:
        harness = SubscriptionSuiteScaleHarness(env, args)
        if args.mode == "plan":
            harness.print_plan()
            return 0
        result = {}
        if args.mode in ("generate", "all"):
            result["generation"] = harness.generate()
        if args.mode in ("benchmark", "all"):
            result["benchmark"] = harness.benchmark()
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2, default=str)
        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        cr.close()


if __name__ == "__main__":
    raise SystemExit(main())
