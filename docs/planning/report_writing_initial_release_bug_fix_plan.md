## Two-Stage Refactor Plan: Idempotent Tagging + Batched Topic Summary Creation

### Summary
Refactor transcript tagging and topic-summary creation to eliminate repeated work, then reduce request overhead with a batch summary API.  
Testing will be split across backend unit/integration and frontend integration (Vitest + MSW). Browser E2E is deferred per your preference.

### Scope
- Improve tagging performance/correctness in `TaggingManager`.
- Add batch topic-summary API and migrate frontend to it.
- Enforce deterministic submit/refresh UX (`Submitting...` until all work completes).
- Add targeted tests for initial states and regressions.

### Out of Scope
- Full browser E2E suite in this refactor (deferred).
- Celery/background jobs (not in this phase).

## Public API / Interface Changes

### 1) New backend endpoint
- Add `POST /api/summaries/batch-topic/` (DRF action on `SummaryViewSet`).

Request body:
```json
{
  "transcript": 123,
  "topics": [10, 11, 12]
}
```

Success response (`201`):
```json
{
  "transcript": 123,
  "results": [
    {"topic": 10, "summary_id": 501, "status": "created"},
    {"topic": 11, "summary_id": 502, "status": "created"},
    {"topic": 12, "summary_id": 503, "status": "created"}
  ]
}
```

Failure response (`500`, fail-entire-request policy):
```json
{
  "error": "TAGGING_FAILED",
  "message": "Failed to classify one or more chunk-topic pairs.",
  "details": [{"topic": 11, "chunk_id": 9001}]
}
```
> **DEV NOTE**: This "fail-entire-request" policy works because `TaggingManager._missing_pairs()` makes `TaggingManager.tag_transcript()` idempotent by identifying missing combinations of chunk/topic from the list of tags in the database for a specific Transcript.

### 2) `TaggingManager` behavior contract changes
- `tag_transcript(topics=...)` becomes idempotent:
1. Load existing chunks for transcript; chunk only when none exist.
2. Compute missing `(chunk_id, topic_id)` pairs from DB.
3. Classify only missing pairs.
4. Persist tags only after successful classification phase.

- LLM initialization happens once per `tag_transcript` run, not per `tag_chunk`.
- Prompt template instantiated once, reused.

### 3) Frontend request flow change
- `NewReportContents` topic summary creation switches from per-topic POST loop to one batch POST.
- `isSubmitting` is set `true` at submit start and reset exactly once at end (single `finally` for whole submit flow).

## Implementation Plan

### Stage 1: Tagging Idempotency + Throughput Internals (Backend)
1. Refactor `TaggingManager`:
- Replace mutable default args (`topics=None`).
- Add `_load_or_create_chunks()` to reuse existing chunks.
- Add `_get_missing_chunk_topic_pairs(topics)` query helper.
- Hoist LLM setup and prompt template outside per-item loop.
- Ensure prompt inputs use `chunk.chunk_text` and `topic.topic`.
- Keep DB writes out of concurrent classification workers.

2. Failure policy implementation:
- Collect all classification results in-memory first.
- If any classification fails, raise and write nothing for that tagging call.
> **DEV NOTE** Is this necessary?  Given the noew idempotent nature of the classification (TaggingManager only tags topic/chunk combos that don't already existing in the DB), we can still write the classification.  This would presumably avoid making unnecessary calls to the API and incurring cost.
- Persist via `Tag.objects.bulk_create(..., ignore_conflicts=True)` after full success.

3. Fix `tgt_topic_obj` scope bug in summary create flow:
- Resolve topic object before branch, reuse in all paths.

4. Queryset efficiency:
- Replace emptiness checks using `len(queryset)` with `.exists()` where only existence is needed.

### Stage 2: Batch Topic Summary API + Frontend Integration
1. Add `batch-topic` action in `SummaryViewSet`:
- Validate transcript and topic IDs.
- Deduplicate incoming topic IDs.
- For each topic, call idempotent `TaggingManager.tag_transcript([topic])`.
- Build summaries for each topic.
- Return structured per-topic result list.

2. Update frontend `new-report-contents.jsx`:
- Keep topic creation step for new topics.
- Aggregate `newlyCreatedTopics + selectedExistingTopicIds`.
- Send one batch summary request.
- Keep submit button in `Submitting...` state until all network work completes.
- Call `onReportsUpdated()` once after successful mutations.

3. Preserve existing single-summary endpoint for backwards compatibility.

## Test Plan

### A) Backend Unit Tests (`missourai_django/transcription/tests/test_tagging.py`)
Initial conditions + expectations:

1. No chunks exist, topic requested:
- `tag_transcript` creates chunks and all expected tags.

2. Chunks already exist, no tags for topic:
- No new chunks created.
- Tags created for all `(existing_chunks x requested_topics)`.

3. Partial tags exist for a topic:
- Only missing `(chunk, topic)` pairs are classified/saved.
- Existing tags are not recomputed.

4. Full tags exist for topic:
- Zero classification calls.
- Zero new tags.

5. LLM setup efficiency:
- `init_chat_model` called once per `tag_transcript` invocation.

6. Failure policy:
- Simulate one classification exception.
- Assert no new tags persisted for that tagging call (fail-entire).

7. Input correctness:
- Assert prompt uses chunk text/topic text primitives, not model object string repr.

### B) Backend API Integration Tests (`missourai_django/transcription/tests/test_api.py`)
1. `POST /api/summaries/` topic, existing complete tags with `topic_present=False`:
- Returns “No content related...” summary.
- No unbound-local error (`tgt_topic_obj` regression test).

2. `POST /api/summaries/` topic, missing tags:
- Tags are generated once.
- Summary created.

3. `POST /api/summaries/batch-topic/` happy path:
- Multiple topics in one request create summaries.
- Per-topic results returned.

4. Batch with duplicate topic IDs:
- Process once per unique topic.

5. Batch with invalid topic ID:
- `400`, no summaries created.

6. Batch with one forced tagging failure:
- `500`, no summaries created in that request (fail-entire).

### C) Frontend Integration Tests (`frontend/__tests__/new-report-contents.test.jsx`)
Use MSW with delayed handlers to assert transitional UI:

1. Submit button state with slow batch summary:
- Click submit -> button text becomes `Submitting...` immediately.
- Remains `Submitting...` until response resolves.
- Reverts to `Submit` only after completion.

2. New-topic + batch-summary flow:
- Topic POST(s) then one batch summary POST.
- `onReportsUpdated` called exactly once after success.

3. Error path:
- Batch summary failure shows error message.
- Button returns to `Submit`.
- `onReportsUpdated` not called.

4. Validation guard:
- Nothing selected -> validation error and no requests fired.

### D) Frontend Page Integration Tests (`frontend/__tests__/generate-report-page-section.test.jsx`)
1. After successful submit + `onReportsUpdated`, page re-fetches summaries/topics.
2. Component switches correctly between `CreateNewReport` and `UpdateExistingReport` based on refreshed data.

### E) E2E (Deferred)
- No Playwright/Cypress in this refactor.
- Add to backlog: one smoke journey for “create new topic summary -> button state -> refreshed summaries visible”.

## Acceptance Criteria
1. Topic summary creation no longer recreates chunks when chunks already exist.
2. For a topic with complete tags, tagging path is a no-op.
3. Frontend sends one topic-summary batch request per submit (not one per topic).
4. Submit button stays in `Submitting...` until all submit work is complete.
5. Batch endpoint obeys fail-entire-request policy on tagging errors.
6. Existing API behavior for single-summary creation remains functional.

## Assumptions and Defaults Chosen
- Failure handling: `Fail Entire Request`.
- API direction: `Batch Endpoint Now`.
- E2E scope: `Deferred`.
- Concurrency default for classification: bounded (start at `max_concurrency=4`, configurable via env in implementation).
- No Celery/background queue in this phase.
