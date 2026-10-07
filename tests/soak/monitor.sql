-- Soak Test Monitoring Queries
-- Run these daily during the 7-day soak test against the staging database.
-- Database: Postgres with Redis for nonce/caching.

-- =============================================================================
-- 1. Heartbeat success rate (pass bar: >= 99.5%)
-- =============================================================================
SELECT
  date_trunc('hour', created_at) AS hour,
  count(*) FILTER (WHERE accepted = true) AS accepted,
  count(*) FILTER (WHERE accepted = false) AS rejected,
  round(100.0 * count(*) FILTER (WHERE accepted = true) / count(*), 2) AS success_rate_pct
FROM ea_heartbeats
WHERE created_at >= now() - interval '7 days'
GROUP BY 1
ORDER BY 1;

-- Overall 7-day heartbeat success rate
SELECT
  round(100.0 * count(*) FILTER (WHERE accepted = true) / count(*), 2) AS success_rate_pct,
  count(*) FILTER (WHERE accepted = true) AS accepted_count,
  count(*) FILTER (WHERE accepted = false) AS rejected_count
FROM ea_heartbeats
WHERE created_at >= now() - interval '7 days';

-- =============================================================================
-- 2. Heartbeat p95 latency (pass bar: < 150ms)
-- =============================================================================
SELECT
  percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms
FROM ea_heartbeats
WHERE created_at >= now() - interval '7 days';

-- =============================================================================
-- 3. Signals stuck outside a final state (hard fail if any > 10min)
-- =============================================================================
SELECT id, state, created_at
FROM signals
WHERE state NOT IN ('EXECUTED', 'REJECTED', 'EXPIRED')
  AND created_at < now() - interval '10 minutes'
ORDER BY created_at ASC;

-- =============================================================================
-- 4. Duplicate executions (hard fail if any)
-- =============================================================================
SELECT signal_id, count(*) AS execution_count
FROM trade_reports
WHERE signal_id IS NOT NULL
  AND retcode IN (10008, 10009)
GROUP BY signal_id
HAVING count(*) > 1;

-- =============================================================================
-- 5. Trades placed while device offline or kill switch on (hard fail if any)
-- =============================================================================
SELECT tr.id, tr.signal_id, tr.device_id, tr.opened_at, tr.realized_pnl
FROM trade_reports tr
JOIN device_presence_events dpe ON dpe.device_id = tr.device_id
  AND dpe.occurred_at <= tr.opened_at
  AND dpe.occurred_at >= tr.opened_at - interval '5 minutes'
WHERE (dpe.presence = 'OFFLINE' OR dpe.kill_switch_active = true)
  AND tr.opened_at >= now() - interval '7 days';

-- =============================================================================
-- 6. API memory growth (check Postgres connection pool + Redis memory)
-- =============================================================================
SELECT count(*) AS active_connections FROM pg_stat_activity WHERE datname = 'onyx';

-- Redis memory usage
SELECT
  used_memory_human,
  used_memory_peak_human,
  (used_memory_peak::float / NULLIF(used_memory, 1)) AS memory_ratio
FROM redis_info
WHERE key = 'Memory';

-- =============================================================================
-- 7. Unhandled errors in Sentry (0 new issues left untriaged)
-- =============================================================================
-- This requires Sentry API access. Example query:
-- SELECT issue_id, title, count(*) AS events
-- FROM sentry_issues
-- WHERE first_seen >= now() - interval '7 days'
--   AND status = 'unresolved'
-- GROUP BY issue_id, title
-- ORDER BY events DESC;

-- =============================================================================
-- 8. EA terminal memory / CPU (flat expected)
-- =============================================================================
-- This is collected via the heartbeat snapshot. Example:
SELECT
  device_id,
  avg((snapshot->>'memory_mb')::float) AS avg_memory_mb,
  max((snapshot->>'memory_mb')::float) AS peak_memory_mb,
  avg((snapshot->>'cpu_pct')::float) AS avg_cpu_pct
FROM ea_heartbeats
WHERE created_at >= now() - interval '7 days'
GROUP BY device_id
ORDER BY peak_memory_mb DESC;
