# 10K Benchmark Report And Performance Budget

## Scope

This report records the first official local 10K Subscription Suite benchmark for Odoo 19 Community. The benchmark used a dedicated database and generated data through the opt-in benchmark harness, not demo XML.

## Environment

| Item | Value |
| --- | --- |
| Benchmark date | 2026-06-26 |
| Database | `odoo19_subscription_benchmark` |
| Odoo version | 19.0 |
| Python | 3.12.10 |
| PostgreSQL | 18.3, 64-bit, Windows |
| OS | Windows 10.0.19044 |
| CPU note | Intel64 Family 6 Model 78 Stepping 3, 4 logical processors |
| RAM note | Not available from sandboxed CIM query |

## Dataset

| Item | Count |
| --- | ---: |
| Subscriptions | 10,000 |
| Plans | 4 |
| Payment recovery samples | 250 |
| MRR movement samples | 250 |
| Deferred revenue schedules | 25 |
| Prefix | `SS-PERF-10K` |

## Commands

```powershell
versions\19.0\venv\Scripts\python.exe scripts\recreate_odoo_database.py odoo19_subscription_benchmark
python scripts\dev_odoo.py --odoo-version 19.0 --port 8079 --no-browser --no-cron -- -d odoo19_subscription_benchmark -i subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init

python scripts\subscription_suite_scale_benchmark.py --odoo-version 19.0 -d odoo19_subscription_benchmark --mode plan --subscriptions 10000 --prefix SS-PERF-10K
python scripts\subscription_suite_scale_benchmark.py --odoo-version 19.0 -d odoo19_subscription_benchmark --mode generate --subscriptions 10000 --auxiliary-count 250 --prefix SS-PERF-10K
python scripts\subscription_suite_scale_benchmark.py --odoo-version 19.0 -d odoo19_subscription_benchmark --mode benchmark --prefix SS-PERF-10K --billing-batch-size 250 --dunning-batch-size 250 --output subscription_suite_scale_benchmark_10k.json
python scripts\subscription_suite_scale_benchmark.py --odoo-version 19.0 -d odoo19_subscription_benchmark --mode benchmark --prefix SS-PERF-10K --billing-batch-size 250 --dunning-batch-size 250 --output subscription_suite_scale_benchmark_10k_rerun.json
```

## Results

### First Benchmark Run

| Job | Time | Result |
| --- | ---: | --- |
| Billing cron | 651.621s | 3,000 new billing attempts |
| Dunning cron | 8.721s | 250 new dunning attempts |
| Recognition preview selection | 0.006s | 50 eligible lines |
| Generated analytics chain | 52.103s | Current company/currency generated |

### Rerun

| Job | Time | Result |
| --- | ---: | --- |
| Billing cron | 0.372s | 0 new billing attempts |
| Dunning cron | 8.839s | 250 new dunning attempts |
| Recognition preview selection | 0.008s | 50 eligible lines |
| Generated analytics chain | 50.881s | Current company/currency regenerated |

## Findings

- Fresh install on the dedicated benchmark database exposed and fixed a billing module import-order issue: the SQL view for manager operations now loads after `subscription.plan.change.request`.
- The first dunning benchmark attempt exposed SMTP as an external dependency because dunning email used forced send. Benchmark mode now queues dunning email through an explicit context flag so the benchmark measures dunning work, not SMTP/network latency.
- Billing cron is idempotent on rerun. The first run processed all due active subscriptions in scope, creating 3,000 attempts; rerun created 0 attempts.
- Dunning cron uses `subscription_suite.dunning_batch_size` as a hard due-work limit. The second run created the next 250 due attempts, with zero duplicate subscription/policy-step pairs.
- Recognition preview remains non-mutating and effectively instant at this dataset size.
- Generated analytics reruns replace generated rows and remain stable at roughly 51-52 seconds for this dataset.

## Current Performance Budget

| Area | Current budget |
| --- | --- |
| First billing pass | About 11 minutes for 3,000 due subscriptions on this local machine |
| Billing rerun with no due work | Under 1 second |
| Dunning batch | About 9 seconds per 250 due subscriptions with benchmark email queueing |
| Recognition preview selection | Under 0.01 seconds for 50 eligible lines |
| Generated analytics chain | About 1 minute for the 10K dataset |

## Follow-Up Candidates

- Decide whether billing cron should add a hard per-run limit in addition to its internal batch grouping.
- Add a cleaner benchmark output mode that flushes progress in real time for long runs.
- Keep SMTP/network delivery out of performance benchmarks unless a dedicated mail-delivery benchmark is explicitly being measured.
- Re-run this report on release-candidate hardware before external publication.
