# Pricing administration and rollout controls

## Permissions and UI

The existing usage page contains pricing administration; no additional Django page is needed.

- `view_all_usage` permits pricing-history reads and readiness checks.
- `manage_usage_pricing` permits previewing and confirming price creation/supersession and readiness checks. It does not grant pricing-history or cross-user usage access. Managers without reporting permission can enter known record IDs and inspect the affected records in their operation preview.
- Users with both permissions can browse all historical/scheduled rates and use the per-record Supersede buttons.
- Existing Django-admin pricing additions remain supported and share the API's write lock. Updates and deletions remain disabled there.

Every API mutation requires a preview followed by explicit confirmation. The preview shows the new record and every existing record to close. It expires after 15 minutes, belongs to the requesting user, and becomes invalid if pricing or configured models change. Confirmation revalidates all rules. Rates and multipliers are transferred as decimal strings, not rounded JavaScript amounts.

## API contract

Use the existing `/api/usage/model-prices/` and `/api/usage/task-pricing/` URLs:

- GET: paginated history; requires reporting permission.
- POST with pricing fields: validate and preview; no persistent changes.
- POST with only `{"confirmation_token": "<token returned by preview>"}`: confirm and create; returns HTTP 201.
- PATCH, PUT, DELETE: not supported.

Both POST operations require pricing-management permission and normal session CSRF protection.

Common fields: `effective_from` (timezone-aware timestamp), optional `effective_to`, and `activate_now` (default false). The backend automatically identifies the pricing record applicable at the activation timestamp. An internal `selected_supersedes` value is accepted only when resolving a selection requested by the preview API; administrators do not enter record IDs in the normal form. Immediate activation uses the exact timestamp shown in the preview and requires a configured model/task combination. Otherwise, a future effective timestamp is required. The UI labels its date inputs as UTC.

Model fields: `model_name`, `billing_unit`, appropriate per-million token rates or `rate_per_minute`; provider is OpenAI and currency is USD. Task fields: `task_type`, `model_name`, and `multiplier`. The preview backend resolves the compatible model-price record applicable at the activation timestamp and signs its exact ID into the confirmation. Administrators never need to enter a model-price ID.

`GET /api/usage/pricing-model-options/?task_type=<task>&at=<timestamp>` returns model choices with pricing compatible with the task at that instant. It requires pricing-management permission, filters transcription to audio-duration rates and summary/tagging to text-token rates, and reports ambiguous model periods separately rather than presenting them as selectable options.

`GET /api/usage/pricing-readiness/` shows each configured task/model using the runtime pricing resolver. Readiness includes billing-unit and model validation, not just existence of a database row.

## Supersession

Supersede an open-ended record in the same scope using a later start. Closing the old period and creating the replacement is atomic. The sole permitted modification to a used price is closing its effective end without excluding recorded usage; rates, multipliers, and historical usage amounts are not rewritten.

Model-price supersession also closes linked task-pricing periods that cross the boundary and atomically carries their multipliers forward to the replacement model price. The preview lists both the closures and replacement task-pricing records. Conflicting scheduled task records or immutable existing ends cause the entire operation to fail and roll back. Task-pricing supersession is independent and retains its model-price ID.

Preview validation temporarily exercises closures inside a transaction and rolls them back; no new price or permanent closure is saved. Confirmed writes and Django-admin additions share a singleton `PricingWriteLock`, including when no price yet exists in the target scope. Runtime preflight remains mandatory.

## Operational model/rate change

Prefer a future UTC activation boundary so all related records can be prepared before traffic reaches it:

1. Add the future ModelPrice. For a rate change to the same model, supersede the old open-ended price. For a different model name, add a new price without superseding an unrelated model's history.
2. Add future TaskPricing for every applicable task, linked to the new ModelPrice and starting at the same boundary. Summary and tagging may share a model but need separate task-pricing records.
3. Run `validate_usage_pricing --at <future timestamp>` with the **intended model environment variables** to validate readiness at that time. Without overrides the command checks the currently configured models.
4. Update `TRANSCRIPTION_MODEL`, `SUMMARY_MODEL`, or `TAGGING_MODEL` in the appropriate runtime environment file.
5. At the effective time, drain old work and restart/recreate web and Celery together with matching configuration. Environment changes require container recreation, not merely a process restart.
6. Confirm the readiness display and inspect a representative successful job.
7. Monitor pending/reconciliation records after deployment, including delivered transcription attempts awaiting billing finalization.

Immediate supersession carries applicable task multipliers forward atomically, so it does not create a task-pricing gap. It can still be rejected if usage was recorded after the preview's proposed boundary or if scheduled/overlapping pricing makes the target ambiguous. Preview again or choose a future boundary; never backdate charges to force a change through.

## Deployment validation

Run from the repository root:

```sh
poetry run python missourai_django/manage.py migrate
poetry run python missourai_django/manage.py validate_usage_pricing
poetry run python missourai_django/manage.py validate_usage_pricing --at 2026-10-01T00:00:00Z
```

The command checks every pricing record's fields and period validity, overlapping model/task periods, supported currency, and current (or requested-time) readiness of all configured tasks. Failures return a nonzero exit code. It does not prove gap-free coverage at every future instant: explicitly validate each planned activation boundary.

The production entrypoint now runs migrations and validation before starting its process. Celery waits for the web service's health check, avoiding concurrent startup migrations. A validation failure prevents production web/workers from starting. Development retains its existing migration-only entrypoint so missing pricing can be configured locally.

When repairing a failed deployment, bypass the normal entrypoint **for an operator command only**, not to start production workers with invalid pricing. For example:

```sh
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/python web manage.py validate_usage_pricing
```

Use the same override for `migrate` or a deliberate operator `shell` session if needed. Preserve/back up the database before operational repairs. Never disable runtime pricing preflight.

No changes to existing prices or usage data are made by deployment validation. This PR includes a schema/data migration only to create and seed the pricing-write mutex; it does not seed new rates or repair historical billing.
