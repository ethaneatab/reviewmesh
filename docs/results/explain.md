# Query paths (scripts/explain_paths.py)

20 000 synthetic records / tasks and 100 000 events in the test databases, `ANALYZE` first. Plans are from `EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)`.

## reconciler: records still STORED, oldest first

expected index: `records_stuck_stored`

```sql
SELECT id FROM intake.records WHERE status = 'STORED' AND updated_at < now() - interval '20 seconds' ORDER BY updated_at LIMIT 50
```
```text
Limit (actual rows=50 loops=1)
  ->  Index Scan using records_stuck_stored on records (actual rows=50 loops=1)
        Index Cond: (updated_at < (now() - '00:00:20'::interval))
```

## timeline: every event of one record, in order

expected index: `record_events_by_record`

```sql
SELECT * FROM intake.record_events WHERE record_id = 'xp_000123' ORDER BY id
```
```text
Sort (actual rows=5 loops=1)
  Sort Key: id
  Sort Method: quicksort  Memory: 25kB
  ->  Bitmap Heap Scan on record_events (actual rows=5 loops=1)
        Recheck Cond: (record_id = 'xp_000123'::text)
        Heap Blocks: exact=5
        ->  Bitmap Index Scan on record_events_by_record (actual rows=5 loops=1)
              Index Cond: (record_id = 'xp_000123'::text)
```

## reviewer queue: open work in one queue, urgent first

expected index: `review_tasks_queue_path`

```sql
SELECT * FROM review.review_tasks WHERE queue = 'finance' AND status = 'OPEN' ORDER BY priority, created_at LIMIT 50
```
```text
Limit (actual rows=50 loops=1)
  ->  Index Scan using review_tasks_queue_path on review_tasks (actual rows=50 loops=1)
        Index Cond: ((queue = 'finance'::text) AND (status = 'OPEN'::text))
```

## audit trail: one record

expected index: `audit_events_by_record`

```sql
SELECT * FROM review.audit_events WHERE record_id = 'xp_000123' ORDER BY id
```
```text
Sort (actual rows=5 loops=1)
  Sort Key: id
  Sort Method: quicksort  Memory: 25kB
  ->  Bitmap Heap Scan on audit_events (actual rows=5 loops=1)
        Recheck Cond: (record_id = 'xp_000123'::text)
        Heap Blocks: exact=5
        ->  Bitmap Index Scan on audit_events_by_record (actual rows=5 loops=1)
              Index Cond: (record_id = 'xp_000123'::text)
```
