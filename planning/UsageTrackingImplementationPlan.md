# Usage Tracking Implementation Plan

This plan implements usage-based billing for transcription, summary generation, and tagging. It supports only `text_tokens` and `audio_duration` billing units, uses `gpt-transcribe` as the default transcription model, fails before any priced API call when pricing is missing or ambiguous, and exposes usage and pricing administration through a single Django/React page at `/usage/`.

Test implementation is intentionally excluded from these to-dos. Creating and validating tests will be handled separately.

## PR 1 — Model Configuration and Billing Foundation

This PR establishes the schema and accounting service without instrumenting API calls yet.

### 1. Centralize active model configuration

- Add these settings to `missourai_web_app/settings.py`:
  - `OPENAI_TRANSCRIPTION_MODEL`, defaulting to `gpt-transcribe`.
  - `OPENAI_SUMMARY_MODEL`, defaulting to `gpt-4.1-mini`.
  - `OPENAI_TAGGING_MODEL`, defaulting to `gpt-4.1-mini`.
- Add the three variables to `.env.example`.
- Pass the variables to both `web` and `celery-worker` in:
  - `docker-compose.yml`
  - `docker-compose.dev.yml`
- Update `TranscriptionManager`, `SummaryManager`, and `TaggingManager` to receive their configured model names from Django settings.
- Remove module-level/default model strings from the managers.
- Ensure each manager exposes the selected model name for pricing and usage recording.
- Document that changing a model requires:
  1. Creating the applicable price records.
  2. Activating the corresponding task-pricing record.
  3. Updating the model environment variable.
  4. Restarting the web and worker processes.

### 2. Add `ModelPrice`

Add an effective-dated model-pricing table:

```text
ModelPrice
- provider
- model_name
- billing_unit
- input_rate_per_million
- cached_input_rate_per_million
- output_rate_per_million
- rate_per_minute
- currency
- effective_from
- effective_to
- created_by
- created_at
```

Supported billing units:

```text
text_tokens
audio_duration
```

Validation rules:

- `text_tokens` requires input and output rates.
- `cached_input_rate_per_million` may be nullable.
- `audio_duration` requires `rate_per_minute`.
- Fields irrelevant to the selected billing unit must be null.
- Rates and dates cannot be negative or invalid.
- `effective_to` must be later than `effective_from`.
- Effective periods cannot overlap for the same provider, model, billing unit, and currency.
- Once referenced by a usage event, a price record cannot be changed or deleted.
- Use `DecimalField` for all rates.

### 3. Add `TaskPricing`

Add the task-specific markup configuration:

```text
TaskPricing
- task_type
- model_price
- multiplier
- effective_from
- effective_to
- created_by
- created_at
```

Task types:

```text
transcription
summary
tagging
```

Validation rules:

- Multiplier must be greater than zero.
- Effective periods cannot overlap for the same task and model price.
- The task-pricing period must fall within its associated model-price period.
- Once referenced by usage, the record cannot be modified or deleted.
- New pricing must supersede old pricing through a new record, not an edit.

### 4. Add the immutable `UsageEvent` ledger

Recommended structure:

```text
UsageEvent
- user
- task_type
- provider
- model_name
- occurred_at
- status
- billing_unit
- usage_source

- input_tokens
- cached_input_tokens
- output_tokens
- audio_duration_seconds

- model_price
- task_pricing
- base_cost
- multiplier
- billed_cost
- currency
- calculation_details

- provider_request_id
- idempotency_key

- transcript
- summary
- tag
- transcription_chunk

- created_at
- updated_at
```

Statuses:

```text
pending
succeeded
failed
reconciliation_required
simulated
```

Usage sources:

```text
provider
duration
simulated
```

Rules:

- Create a pending event before making an external API call.
- Snapshot the resolved model, pricing records, rates, and multiplier at that point.
- Only `succeeded` events contribute to billed totals.
- `simulated` events have zero base and billed costs.
- Artifact relationships remain nullable initially because the event is created before the model response and artifact.
- Completed financial fields become immutable.
- `idempotency_key` is unique.
- Use `DecimalField` for money and billable duration.
- Add indexes for user/date, task/date, status/date, and artifact relationships.

Creating a pending record first does not make the API and database transaction fully atomic, but it ensures there is an audit record if processing fails after pricing resolution.

### 5. Add permissions

Define:

```text
transcription.view_all_usage
transcription.manage_usage_pricing
```

- Regular authenticated users need no special permission to view their own usage.
- `view_all_usage` grants access to other users and aggregate organization data.
- `manage_usage_pricing` grants access to pricing mutations.
- Create Django groups for these permission sets.
- Assign the applicable permission/group to Andrew and administrators through deployment setup rather than hard-coding an email in application logic.

### 6. Add the pricing service

Create a centralized service responsible for all pricing decisions:

```text
resolve_pricing(task_type, provider, model_name, occurred_at)
create_pending_usage_event(...)
complete_token_event(...)
complete_duration_event(...)
mark_failed(...)
mark_reconciliation_required(...)
```

Responsibilities:

- Resolve exactly one applicable `ModelPrice`.
- Resolve exactly one applicable `TaskPricing`.
- Reject missing or ambiguous pricing.
- Create the pending ledger event.
- Calculate costs deterministically.
- Store the complete calculation inputs in `calculation_details`.
- Apply the configured multiplier.
- Use consistent decimal rounding.

Calculation formulas:

```text
Text base cost =
    input_tokens × input_rate / 1,000,000
  + cached_input_tokens × cached_rate / 1,000,000
  + output_tokens × output_rate / 1,000,000
```

Cached tokens must not also be charged as ordinary input tokens. The service should normalize provider metadata into uncached input, cached input, and output counts before calculating.

```text
Duration base cost =
    audio_duration_seconds / 60
  × rate_per_minute
```

```text
Billed cost = base cost × multiplier
```

### 7. Seed initial pricing

Create initial active records for:

- `gpt-transcribe` with `audio_duration` billing.
- `gpt-4.1-mini` with `text_tokens` billing.
- Transcription multiplier: `4`.
- Summary multiplier: `4`.
- Tagging multiplier: `4`.

The effective timestamp should be explicit and aligned with deployment—not generated implicitly every time migrations run.

The seeded OpenAI rates should be documented as initial operational configuration, not permanently authoritative constants.

## PR 2 — Model-Call Instrumentation

This PR integrates the ledger into transcription, summary generation, and tagging.

### 1. Add a common billable-call lifecycle

For every model call:

1. Determine the task, provider, configured model, and timestamp.
2. Resolve applicable pricing.
3. Create a pending `UsageEvent`.
4. Make the external request.
5. Extract actual usage.
6. Create or update the generated artifact.
7. Complete the event with usage and cost.
8. Mark the event failed or requiring reconciliation when processing cannot finish.

The pricing check must happen before the API request.

### 2. Instrument transcription

Update `TranscriptionManager` to:

- Use `settings.OPENAI_TRANSCRIPTION_MODEL`.
- Pass the model name into existing `TranscriptionJobMetric` records.
- Carry the duration of each actual submitted audio chunk into the API-call layer.
- Resolve duration pricing before submitting each chunk.
- Create one usage event for each actual external transcription request.
- Use the submitted chunk's duration as the billable quantity.
- Associate the completed event with:
  - User
  - Transcript
  - `TranscriptionJobMetric`
  - `TranscriptionChunkMetric`
- Store the configured per-minute rate snapshot for `gpt-transcribe`.
- Record split and retry calls separately because each submitted audio request can incur cost.
- Use a stable idempotency format containing the background job, logical chunk identity, split depth/path, and attempt identifier.
- Mark development-mode calls as simulated with zero cost.
- Mark a pending event for reconciliation if an API response is received but usage finalization or artifact persistence fails.

Because `gpt-transcribe` is duration-priced, no audio-token calculation or backward-compatible audio-token billing path will be implemented.

### 3. Instrument summaries

Refactor `SummaryManager` to:

- Use `settings.OPENAI_SUMMARY_MODEL`.
- Resolve pricing before invoking the model.
- Avoid parsing directly to a string before usage metadata is captured.
- Retain the raw AI response.
- Extract input, cached-input, and output token counts from provider metadata.
- Parse the response text after recording the raw metadata.
- Create and associate the resulting `Summary`.
- Complete the usage event with the provider's token counts.
- Mark development-mode calls as simulated.
- Preserve general-summary and topic-summary behavior.

The generated summary and its usage event should be saved together after the external response. If that persistence fails, retain the pending event for reconciliation.

### 4. Instrument tagging

Refactor `TaggingManager` to:

- Use `settings.OPENAI_TAGGING_MODEL`.
- Preserve raw response and usage metadata while continuing to use structured output.
- Create one pending usage event per chunk/topic model invocation.
- Link each successful event to the resulting `Tag`.
- Store provider-reported text-token usage.
- Generate a stable idempotency key using transcript, chunk, topic, tagging run, and invocation identity.
- Mark development-mode calls as simulated.
- Prevent accidental reuse of an existing event for an intentionally repeated tagging operation.

### 5. Clarify regeneration behavior

- Introduce an explicit run identifier for tagging operations.
- Distinguish an intentional regeneration from a retry of the same call.
- Ensure retries use the same logical operation identity.
- Ensure an intentional regeneration receives a new run identity and produces new billable events.
- Avoid creating duplicate chunks merely because tagging was requested for an additional topic.
- Reuse existing transcript chunks when possible.

### 6. Add operational logging

Log structured identifiers without logging prompts or transcript contents:

- Usage event ID
- User ID
- Task
- Model
- Background job ID
- Provider request ID
- Artifact ID
- Status transition
- Pricing-resolution failure
- Reconciliation requirement

## PR 3 — Usage Reporting API and Page Shell

This PR exposes the reporting/query layer while keeping the frontend minimal.

### 1. Add the `/usage/` Django route

Add to `ui_urls.py`:

```python
path("usage/", views.usage, name="usage")
```

The view must:

- Require authentication.
- Render `transcription/usage.html`.
- Seed API URLs.
- Seed capability flags.
- Avoid embedding financial or cross-user data directly in the HTML.

Initial payload:

```json
{
  "apiUrls": {
    "summary": "...",
    "events": "...",
    "users": "...",
    "modelPrices": "...",
    "taskPricing": "..."
  },
  "capabilities": {
    "canViewAllUsage": false,
    "canManagePricing": false
  },
  "defaults": {
    "currency": "USD",
    "timezone": "UTC"
  }
}
```

The capability fields control presentation only; DRF remains authoritative.

### 2. Add `usage.html`

Create a single Django template that:

- Extends `transcription/base.html`.
- Adds `#usage-root`.
- Exposes the initial payload through `json_script`.
- Loads `src/usage.jsx`.
- Contains no separate administrative dashboard markup.

A custom template tag is not needed unless usage UI is later embedded in another page.

### 3. Add the Vite entry

- Create `frontend/src/usage.jsx`.
- Add it to `rollupOptions.input` in `frontend/vite.config.js`.
- Allow Vite to generate `manifest.json`; do not edit the manifest manually.
- Reuse `getInitialData`.
- Reuse the common CSRF helper for pricing mutations.

### 4. Add reporting serializers

Create dedicated serializers for:

- Monthly task totals.
- User monthly totals.
- Overall monthly totals.
- Applied pricing-period details.
- Usage-event detail rows.
- User filter choices.
- Model-price records.
- Task-pricing records.

Aggregate serializers should be plain DRF serializers rather than `ModelSerializer` where no direct model representation exists.

### 5. Add a usage-reporting service

Centralize reporting queries outside the viewsets:

```text
get_month_bounds(month, timezone)
get_user_summary(...)
get_organization_summary(...)
get_task_breakdown(...)
get_event_details(...)
get_applied_pricing_periods(...)
```

Rules:

- Default to the current calendar month through the current instant.
- Use half-open timestamp ranges.
- Aggregate stored `base_cost` and `billed_cost`.
- Never recalculate historical events against current price records.
- Include only succeeded events in billed totals.
- Expose failed, pending, and reconciliation events in operational counts where authorized.
- Avoid using client-supplied timezone values for billing-period definitions.

### 6. Add read-only usage APIs

Suggested endpoints:

```text
GET /api/usage/summary/
GET /api/usage/events/
GET /api/usage/users/
```

Supported filters:

- `month=YYYY-MM`
- `user_id`
- `task_type`
- `model_name`
- `status`
- Event pagination

Authorization:

- Normal users are always scoped to `request.user`.
- Supplying another `user_id` requires `view_all_usage`.
- Organization-wide results require `view_all_usage`.
- The user list requires `view_all_usage`.
- Cross-user access must be rejected by the backend regardless of frontend capabilities.

### 7. Add applied-pricing reporting

The summary response should include both:

- Aggregated monthly totals.
- The pricing periods contributing to those totals.

This supports a month where rates or multipliers changed partway through the period without recalculating individual events.

### 8. Add navigation

- Add a “Usage” link for all authenticated users.
- Keep the same URL regardless of permission.
- Do not add a separate administrative navigation link.

## PR 4 — React Usage Dashboard

This PR implements the read-only dashboard experience.

### 1. Build the shared page structure

Create a single usage application containing:

- Month selector.
- Current period indicator.
- Overall charged total.
- Base-cost total where the user is allowed to see it.
- Task breakdown for transcription, summaries, and tagging.
- Usage-event drill-down.
- Loading, empty, and error states.

### 2. Implement personal usage mode

For users without `view_all_usage`:

- Fetch only personal data.
- Do not render user-selection controls.
- Show task totals and monthly total.
- Show personal event detail.
- Do not expose underlying model rates or multipliers unless that is explicitly desired later.
- Do not include links or controls for pricing management.

### 3. Implement privileged reporting mode

For users with `view_all_usage`:

- Add an “All users” option.
- Add individual-user selection.
- Display one row per user in organization mode.
- Display task-level base and billed costs.
- Display monthly totals.
- Display event counts and pricing periods.
- Allow filtering by task and model.
- Make reconciliation/pending counts visible.

### 4. Implement pricing-period display

For privileged users, show:

- Provider.
- Model.
- Billing unit.
- Effective period.
- Input/cached/output token rates where applicable.
- Per-minute rate where applicable.
- Task multiplier.
- Base cost attributable to the period.
- Billed cost attributable to the period.

### 5. Keep frontend authorization passive

- Use capability flags to decide which controls to render.
- Do not treat hidden components as access control.
- Handle API `403` responses cleanly.
- Clear privileged data from React state when switching out of an authorized scope or after permission-related errors.

## PR 5 — Pricing Administration and Rollout Controls

This PR adds the privileged workflow for managing future rates.

### 1. Add pricing-management APIs

Suggested endpoints:

```text
GET  /api/usage/model-prices/
POST /api/usage/model-prices/

GET  /api/usage/task-pricing/
POST /api/usage/task-pricing/
```

Optional detail endpoints should remain read-only after a record has been used.

Authorization:

- Pricing reads require `view_all_usage`.
- Pricing creates require `manage_usage_pricing`.
- Superseding active pricing requires `manage_usage_pricing`.
- Used records cannot be updated or deleted.

### 2. Implement transactional supersession

When creating a new active price:

1. Lock the current applicable record.
2. Validate the new effective timestamp.
3. Set the old record's end to the new start.
4. Create the new record.
5. Commit both changes atomically.

Do this separately for `ModelPrice` and `TaskPricing`.

Reject:

- Overlapping periods.
- Invalid rates.
- Unsupported billing-unit/rate combinations.
- Task pricing outside the model-price period.
- A task/model combination inconsistent with active application configuration when immediate activation is requested.

### 3. Add pricing management to the React page

For users with `manage_usage_pricing`:

- Add a pricing-management section within `/usage/`.
- Show active and historical model prices.
- Show active and historical task multipliers.
- Provide “Add new price” and “Supersede” workflows.
- Preview which existing record will be closed.
- Show the effective timestamp and resulting configuration.
- Require explicit confirmation before saving.
- Refresh dashboard pricing data after successful mutation.

### 4. Add active-model readiness display

Show administrators whether each configured task is billable:

```text
Transcription | gpt-transcribe | Pricing active
Summary       | gpt-4.1-mini   | Pricing active
Tagging       | gpt-4.1-mini   | Pricing active
```

The backend should calculate this readiness state using the same pricing resolver used before API calls.

### 5. Add startup/deployment validation

Add a management command such as:

```text
python manage.py validate_usage_pricing
```

It should verify:

- Every configured model has an active `ModelPrice`.
- Every task/model pair has active `TaskPricing`.
- Billing units and rate fields are valid.
- No effective periods overlap.
- Currency is supported.

Run this command in the deployment workflow before starting production workers. Runtime preflight remains mandatory even when deployment validation passes.

### 6. Document the operational model-change procedure

Document:

1. Create the future `ModelPrice`.
2. Create the future `TaskPricing`.
3. Validate the pricing configuration.
4. Change the model environment variable.
5. Deploy/restart web and Celery workers at the effective time.
6. Confirm the active-model readiness display.
7. Monitor pending/reconciliation events after deployment.

## Rollout Sequence

1. Deploy PR 1 with tables, pricing records, permissions, and configuration.
2. Run pricing validation.
3. Deploy PR 2 to begin collecting usage.
4. Review stored usage events and reconcile representative totals operationally.
5. Deploy PR 3 to expose the secured reporting APIs and `/usage/` shell.
6. Deploy PR 4 to expose dashboards.
7. Deploy PR 5 to allow pricing administration through the application.

This order starts collecting billing data before the dashboard is finished while preventing any model request from proceeding without active pricing.

## Settled Implementation Decisions

- Transcription defaults to `gpt-transcribe`.
- Supported billing units are only `text_tokens` and `audio_duration`.
- No audio-token compatibility layer will be built.
- Missing or ambiguous pricing blocks the model call.
- Billing is based on immutable per-call usage events.
- Active models are configured through Django settings and environment variables.
- Rates and multipliers are effective-dated and historically immutable.
- `/usage/` is the only dashboard route.
- One Django template mounts one React application.
- Dashboard and pricing data come from DRF.
- Permissions control cross-user reporting and pricing administration.
- Currency begins as USD.
- Internal calculations retain high decimal precision.
- Historical pre-implementation usage will not be reconstructed.
- Test implementation is deliberately outside this plan.
