# Delivery-based transcription billing

## Data ownership and lifecycle

`Transcript` holds the delivered text. `TranscriptionBillingAttempt` links a background job to its transcript and coordinates delivery and billing. Its `usage_events` relation contains the provider-request records; it is not an additional charge.

For a new transcription, events start `pending`. Successful provider responses move to `awaiting_delivery`, with known `base_cost` and no finalized `billed_cost`. Saving the assembled text and marking the attempt `delivered` happen in one short transaction. A separate short transaction finalizes all eligible charges together. No provider request runs inside either transaction.

When A and C succeed but B fails irrecoverably:

| Record | Processing/provider outcome | Billing/event status | Customer charge |
| --- | --- | --- | --- |
| Attempt | `failed` | `not_billable` | No separate charge |
| A event | `succeeded` | `not_billable` | 0 |
| B event | `failed` | `failed` | 0 |
| C event | `succeeded` | `not_billable` | 0 |

Known provider costs are retained. Unknown costs remain null, not zero. A failure before pending-event creation has no UsageEvent because no provider request was started. A response-validation failure can initially require reconciliation instead of having a confirmed provider outcome. The failed attempt still prevents customer charges.

Already-running chunks may finish after an attempt is closed. Their nonbillable events can receive late provider evidence but cannot become charges. Finalized successful events remain immutable. A failure of a parent request that is successfully recovered by splitting its audio range does not invalidate delivery; failed requests themselves are not charged. Exhausted fallback and rejected too-short ranges now fail the transcription rather than silently producing partial output.

If billing finalization fails after delivery, the transcript stays available. The attempt becomes `reconciliation_required` where possible; otherwise its durable `delivered` / `pending` state remains discoverable. Charges are rolled back together. A later tagging failure does not revoke transcription delivery or its valid charges.

## Deployment and recovery

Drain existing transcription work, apply migrations, and restart web and Celery together. Do not mix workers running the old immediate-charge lifecycle with the new lifecycle. No historical-event repair or development-data reset is included.

From the repository root:

```powershell
poetry run python missourai_django/manage.py migrate
poetry run python missourai_django/manage.py reconcile_transcription_billing
poetry run python missourai_django/manage.py reconcile_transcription_billing --attempt-id 123
```

The recovery command only finalizes delivered attempts with sufficient stored evidence. It never calls a provider, guesses missing usage, or reprices at current rates. Unresolved evidence produces a nonzero exit and remains flagged for operator review. After verifying/correcting missing evidence through the validated usage service, rerun finalization. There is no new reconciliation permission group or writable admin action; attempts are read-only in admin under `view_all_usage`.

Run this command periodically through your deployment scheduler if automatic recovery is desired; no scheduler configuration is installed by this change.

For an abandoned worker, first verify that the original worker has stopped. Then explicitly close the specific attempt:

```powershell
poetry run python missourai_django/manage.py reconcile_transcription_billing --attempt-id 123 --abandon --reason "Worker terminated; no transcript delivered"
```

This fences later delivery and closes outstanding customer charges as nonbillable. It does not reconstruct lost text or automatically retry transcription. Duplicate Celery task deliveries do not restart paid work. Deliberate transcription retries require a new background job/attempt; automatic chunk reuse and upload retention are not added.

## Reporting

Existing totals still include only `succeeded` events. The new statuses are supported in existing filters, and event details include attempt identity and provider outcome. The transcript page derives processing/failure messages from the attempt rather than storing a progress message as transcript text.

Privileged aggregate base cost still means provider cost associated with finalized charges, not all provider expenditure. Nonbillable provider costs remain inspectable in event details/admin.

## Verification and existing test updates

No persistent test files were changed. Isolated verification covered mixed chunk outcomes, late results, blocked late delivery, all-success finalization, idempotent billing recovery, incomplete evidence, injected mid-finalization rollback, transcript-save failure, concurrent chunk execution, and duplicate task delivery. Provider calls were mocked; application data was not modified.

Existing manager tests need to create a `TranscriptionBillingAttempt` linked to their job/transcript. Before the task saves text, successful manager calls should now leave events `awaiting_delivery` with null `billed_cost`. Mock `record_transcription_usage` in the manager instead of its former `complete_duration_event` import. Exhausted extraction fallback should raise, not return a warning marker. Upload tests should expect empty initial transcript text and a processing attempt instead of a stored progress string.
