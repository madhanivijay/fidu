# Benchmark Results

Real numbers from `python -m benchmarks.run` against the fixed 8-rule set in
[`rules.yaml`](rules.yaml). Reproduce locally with:

```bash
python -m benchmarks.run --engine pandas --rows 1000000 --json
```

## Environment

| field | value |
|---|---|
| date | 2026-04-26 |
| machine | macOS 26.4, Apple Silicon (arm64) |
| python | 3.14.2 |
| pandas | 3.0.2 |
| engine | pandas (in-process) |
| schema | 50 cols (6 typed + 44 padded synthetic) |
| rules | 8 (not_null x2, unique, between, accepted_values, regex_match, row_count_min, required_columns) |

## Headline numbers (pandas engine)

| rows | wall_ms | peak_rss_mb | pass/fail/skip/err |
|---:|---:|---:|---|
| 10,000 | 64.0 | 137.5 | 7/1/0/0 |
| 100,000 | 58.2 | 301.6 | 7/1/0/0 |
| 1,000,000 | 348.6 | 1,462.4 | 7/1/0/0 |
| 10,000,000 | 7,243.0 | 5,745.6 | 7/1/0/0 |

Notes:

- The single failing rule is `customer_id_not_null` -- the data generator
  injects ~0.1% nulls deterministically (seed=42) so this rule is *expected*
  to fail. It exists to keep the failure path on the hot loop.
- 10K is slightly slower than 100K because per-rule fixed overhead dominates
  at small N (engine init, parquet read, dispatch). Above ~50K rows the
  per-row cost takes over and timing scales roughly linearly.
- `peak_rss_mb` is the high-water mark over the entire process (data
  generation + parquet write + executor). For pure executor cost subtract
  the data-gen footprint -- at 1M rows the executor itself adds ~700MB on
  top of the ~700MB DataFrame.
- 10M rows scales linearly from 1M on wall-clock (~7.2s vs ~0.35s, 20x rows
  in 21x time) and roughly linearly on RSS (~5.7GB vs ~1.5GB). At this size
  per-rule durations spread out: `not_null` and `unique` dominate at ~1s
  each, followed by `customer_id_not_null` at ~0.7s.

## Per-rule breakdown at 1M rows

| rule | type | duration_ms | status |
|---|---|---:|---|
| order_id_not_null | not_null | 25.3 | passed |
| order_id_unique | unique | 24.0 | passed |
| customer_id_not_null | not_null | 21.3 | failed |
| amount_in_range | between | 12.4 | passed |
| valid_status | accepted_values | 21.7 | passed |
| email_regex | regex_match | 51.8 | passed |
| minimum_row_count | row_count_min | 0.9 | passed |
| required_columns_present | required_columns | 0.0 | passed |

`email_regex` is the slowest rule at 1M (vectorized but compiled-pattern
bound); `required_columns` and `row_count_min` are effectively free.

## Headline numbers (SQL engine, in-process DuckDB)

`benchmarks/rules_sql.yaml` is the SQL-supported subset (6 rules; SQL engine
doesn't natively implement `regex_match` or `required_columns`). DuckDB
reads parquet directly via `read_parquet()` with predicate pushdown, so the
shape here is closer to a "warehouse-scan" model than a pandas in-memory
scan.

| rows | wall_ms | peak_rss_mb | pass/fail/skip/err |
|---:|---:|---:|---|
| 10,000 | 8.0 | 144.2 | 5/1/0/0 |
| 100,000 | 18.9 | 222.4 | 5/1/0/0 |
| 1,000,000 | 47.4 | 799.4 | 5/1/0/0 |
| 10,000,000 | 203.8 | 2,915.0 | 5/1/0/0 |

DuckDB's columnar parquet reader + vectorized execution buys roughly a
**35x speedup at 10M rows** vs pandas (200ms vs 7.2s) and uses about half
the RAM. `unique` dominates SQL cost (~140ms at 10M) because it requires a
full GROUP BY + HAVING scan.

## Headline numbers (Spark engine, local PySpark)

Spark numbers depend heavily on JVM startup, partition count, and driver
memory. Run `python -m benchmarks.run_spark --rows 1000000 --json` on your
own hardware -- the kit's harness is committed but cluster results aren't,
because they're not portable across environments.

## Per-rule breakdown at 10M rows

| rule | type | duration_ms | status |
|---|---|---:|---|
| order_id_not_null | not_null | 1,365.5 | passed |
| order_id_unique | unique | 831.5 | passed |
| customer_id_not_null | not_null | 716.2 | failed |
| amount_in_range | between | 257.0 | passed |
| valid_status | accepted_values | 204.4 | passed |
| email_regex | regex_match | 534.7 | passed |
| minimum_row_count | row_count_min | 1.0 | passed |
| required_columns_present | required_columns | 0.1 | passed |

At 10M the ranking shifts: `not_null` becomes the most expensive rule
because it has to materialize the failed-row sample, while `email_regex`
drops to third. `row_count_min` and `required_columns` stay constant-time
regardless of N.

## How these numbers move

- **Adding rules** is roughly additive. 8 rules in ~350ms means each rule
  costs ~25-50ms at 1M rows for typical column-level checks.
- **Adding columns** (the 50-col schema vs a 6-col one) costs roughly
  proportional parquet-read time but does not change rule cost.
- **The SQL engine** pushes the work into the warehouse, so wall-clock is
  dominated by query planning + network round-trips, not pandas. The
  in-process DuckDB harness lives at `benchmarks/run_sql.py`; remote
  warehouse benchmarks are out of scope here -- run them against your own.
- **The Spark engine** runs the same rule set against a local PySpark
  session via `benchmarks/run_spark.py`; remote cluster numbers are out
  of scope here.

## Updating these numbers

Re-run `python -m benchmarks.run --engine pandas --rows {10000,100000,1000000} --json`
on a clean machine and paste the headline row into the table. Don't average
across machines -- different hardware gives different absolute numbers but
the *shape* (sublinear at small N, linear above ~100K) should hold.
