# Runbook: Downstream Dependency Outage

## Symptoms

- Logs show timeout or connection-refused errors when calling a specific downstream service (e.g.,
  `payment-api`, an external API, or another internal service).
- Latency on the calling service spikes, often clustered right at the configured timeout value (requests
  hang until they time out).
- Error rate on the calling service rises even though its own deploy history shows no recent change.

## Likely causes

1. The downstream dependency itself is down, degraded, or rate-limiting the caller.
2. A network/DNS issue between the caller and the dependency.
3. A deploy on the *calling* service changed timeout/retry settings in a way that amplifies a minor downstream
   blip into a major incident (check this before assuming the dependency is fully at fault).

## Diagnosis steps

1. Confirm the errors are all directed at the same downstream dependency (check the log messages/target
   field).
2. Check whether the calling service's own deploy history shows a change at the same time — if not, the
   issue is likely external.
3. Check whether latency values cluster at the timeout threshold (a strong signal of calls hanging until
   timeout, not fast failures).

## Fix

- If the dependency is external and down: apply circuit breaking / fallback behavior if available, and wait
  for the dependency to recover. Escalate to the dependency's owning team.
- If caused by a recent timeout/retry config change: roll back that change.

## Prevention

- Add circuit breakers so one slow dependency can't exhaust threads/connections in the calling service.
- Track dependency health separately so outages are attributed correctly instead of paging the wrong team.
