# Runbook: Memory Leak / Repeated Restarts

## Symptoms

- A service's memory usage climbs steadily over time instead of staying flat or sawtoothing with garbage
  collection.
- Logs show `OutOfMemoryError` (or equivalent) shortly before the process restarts.
- The service restarts repeatedly, each restart followed by memory climbing again from a low baseline.

## Likely causes

1. **A recent deploy introduced a leak** (e.g., an unbounded cache, a listener that's never removed, objects
   held in a growing collection). Check deploy history for the affected service.
2. A configuration change increased load per instance (e.g., batch size, cache TTL) without a code change —
   less common, check deploy diffs for config-only changes too.

## Diagnosis steps

1. Find when memory usage started trending upward using the metrics tool (rolling z-score on the memory
   series will flag the inflection point).
2. Find the first `OutOfMemoryError` log line's timestamp — this is typically well after the trend starts,
   once memory crosses the limit.
3. Check deploy history for the affected service; the leak-introducing deploy should be at or before the
   point memory starts trending upward.

## Fix

- Roll back to the last known-good version.
- File a follow-up to fix the leak properly (don't just restart services on a loop as a permanent fix).

## Prevention

- Add memory-growth alerting (not just absolute-threshold alerting) so slow leaks are caught before OOM.
- Require load testing for services that introduce new caches or long-lived collections.
