# Runbook: Database Connection Pool Exhausted

## Symptoms

- Logs show repeated `pool exhausted` / `connection pool exhausted` errors from a service that talks to the
  database (commonly `checkout`, `cart`, or `db`).
- Latency (p95/p99) on the affected service spikes sharply.
- Error rate rises alongside the latency spike.
- DB connection count metric sits at or near the configured pool max.

## Likely causes

1. **A recent deploy reduced the connection pool size** in service config. Check deploy history for the
   affected service around the time the errors started — this is the most common cause.
2. A spike in traffic exceeded a pool sized correctly for normal load (less common; check if request volume
   also spiked at the same time).
3. A downstream slowdown (e.g., slow queries) caused connections to be held longer than usual, starving the
   pool even though its size didn't change.

## Diagnosis steps

1. Find the first `pool exhausted` log line's timestamp.
2. Check the deploy history for the affected service in the window just before that timestamp.
3. Confirm the latency/error-rate anomaly starts at or after the deploy, not before — the cause must precede
   the symptom.
4. Compare the pool size/config in the new deploy against the previous version.

## Fix

- **If caused by a bad deploy**: roll back to the previous version. Pool size should return to its prior,
  working value.
- **If caused by traffic growth**: increase pool size and add autoscaling for the service, not just a rollback.
- **If caused by slow queries**: investigate the slow query first; increasing pool size only masks the problem.

## Prevention

- Add a config validation/review step for connection pool size changes.
- Alert when DB connection count exceeds 80% of pool max, before it's fully exhausted.
