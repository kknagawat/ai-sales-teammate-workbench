# AI Sales Teammate Workbench

A secure review workbench for AI-generated sales follow-up emails. Reviewers can log in, inspect assigned lead work items, review the AI decision trace, edit drafts, regenerate with feedback, approve, reject, and inspect audit history.

## Setup

```bash
docker compose up -d

cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
uv run celery -A app.workers.celery_app worker --loglevel=info --concurrency=2

cd ../frontend
pnpm install
pnpm dev
```

Frontend: `http://localhost:3000`
Backend: `http://localhost:8000`
Worker log file: `backend/logs/worker.log`

Local reviewer signup invite code: `demo-reviewer-code` (demo-only; production startup rejects it)

## Free Deployment

The root `render.yaml` is configured for a no-paid-Render-services deployment:

- Vercel free hosts the Next.js frontend.
- Render free hosts one Python web service.
- The Render web service runs both FastAPI and Celery in one process group via `backend/scripts/render_free_start.sh`.
- Neon or Supabase free provides Postgres.
- Upstash free provides Redis.

This is intentionally a demo-friendly deployment shape. It avoids a paid Render background worker, but it means the worker sleeps whenever the Render free web service sleeps. For a production deployment, run the API and worker as separate always-on services.

Render Blueprint inputs:

- `FRONTEND_ORIGIN`: your Vercel production URL, for example `https://your-app.vercel.app`
- `DATABASE_URL`: Neon/Supabase Postgres connection string
- `REDIS_URL`: Upstash Redis connection string
- `REVIEWER_INVITE_CODE`: a private 12+ character invite code

The start command runs migrations before starting the app:

```bash
uv run alembic upgrade head && bash scripts/render_free_start.sh
```

If you use Neon and the URL includes `?sslmode=require`, the backend normalizes it for async SQLAlchemy while preserving a sync-compatible URL for the Celery worker.

## Architecture

- Frontend: Next.js App Router with a same-origin `/api/backend/*` proxy.
- Backend: FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Redis-ready runtime config.
- Auth: signup/login with bcrypt passwords and JWT in an httpOnly host-only cookie.
- Tenancy: every work item and audit query is organization-scoped; cross-org access returns `404`.
- Workflow: state machine plus `last_seen_version` optimistic concurrency and row locks on mutations.
- Worker: Celery processes approval jobs with a sync SQLAlchemy session and fake email/CRM side effects.
- AI: provider interface with mock and Anthropic implementations behind one contract and an admin runtime switch.

## Product Decisions

- Approval is an action that moves an item to `PROCESSING`; the audit log records who approved what.
- Approved sends use `approved_draft_snapshot`, not the mutable live draft.
- Regeneration marks an item `REGENERATING`, calls the provider outside the DB lock, then saves or fails in a second transaction.
- Approval uses an idempotency key plus DB-backed active-job protection to avoid duplicate sends.
- Conflict responses include a machine-readable code so the frontend can distinguish stale data from invalid actions.
- If Redis enqueue fails after approval commits, the app marks the job and item `FAILED` and writes `JOB_FAILED` so reviewers can retry instead of waiting on a stuck `PROCESSING` item.
- Retry processing can recover failed items, missing processing jobs, and stale active jobs while blocking fresh active jobs to avoid duplicate sends.
- Signup supports two safe paths: create a new organization as the first admin, or join an existing organization as a reviewer with the server-side invite code.
- Signup bootstraps demo work items by default (`SIGNUP_DEMO_DATA_ENABLED=true`) so new admins and reviewers can immediately review realistic leads.
- Admins can switch their organization's active AI provider at runtime when `LLM_RUNTIME_SWITCHING_ENABLED=true`. The switch is process-local, org-scoped, audited, guarded server-side, and Claude can only be selected when the backend has `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` configured.

## Background Processing

Approving a work item creates a real `background_jobs` row and enqueues `process_approval(job_id)` in Celery. The worker uses the sync SQLAlchemy session, reads `approved_draft_snapshot`, simulates sending the email, simulates a CRM sync, creates a fake CRM activity id, and then moves the item from `PROCESSING` to `SENT`.

Worker evidence is visible in three places:

- the item status changes in the UI
- `JOB_STARTED` and `JOB_COMPLETED` or `JOB_FAILED` entries appear in the audit timeline
- `backend/logs/worker.log` records task received, job started, fake email send, fake CRM sync/activity creation, completion, failure, and retry scheduling

For local demos, run the API, frontend, and Celery worker as three separate processes. If an approved item remains in `PROCESSING`, first confirm the worker is running:

```bash
cd backend
uv run celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
```

Watch worker activity during a demo with:

```bash
tail -f backend/logs/worker.log
```

The worker log deliberately avoids secrets and full draft bodies. It records ids, status transitions, fake message/activity ids, and the approved draft hash instead of the email body. The local file uses simple size-based rotation.

## Status Updates

The frontend uses polling instead of WebSockets or SSE to keep the infrastructure simple for the assignment.

- Queue page: polls every 5 seconds only when visible work items include `PROCESSING` or `REGENERATING`.
- Detail page: polls every 2 seconds only when the current item is `PROCESSING` or `REGENERATING`.
- Polling stops when the item returns to `PENDING_REVIEW`, `SENT`, `FAILED`, or `REJECTED`.
- React Query disables refetching in the background for these polling queries, so hidden tabs do not keep hammering the API.

This gives reviewers visible transitions for approval and regeneration without running a persistent socket service.

## Audit Log

Important actions are persisted in `audit_logs`, scoped by organization:

- `ITEM_CREATED`
- `AI_DRAFT_GENERATED`
- `DRAFT_REGENERATION_STARTED`
- `DRAFT_REGENERATED`
- `DRAFT_REGENERATION_FAILED`
- `DRAFT_EDITED`
- `ITEM_APPROVED`
- `ITEM_REJECTED`
- `JOB_STARTED`
- `JOB_COMPLETED`
- `JOB_FAILED`
- `RUNTIME_PROVIDER_CHANGED`

Each audit row stores the organization, optional work item, optional actor, action, timestamp, metadata, IP address, and user agent when available. Worker-created entries set `actor_user_id = null` and include job metadata. Runtime provider changes are admin-authored and org-scoped.

## Security Recommendations For Production

The assignment implementation includes server-side authz, tenant scoping, httpOnly cookies, origin checks, row locks, stale-version checks, idempotency for approval, safe public config, and no browser-exposed LLM secrets. For production, I would add:

- per-organization invite records with expiration, single-use consumption, and audit history
- email verification for signup
- server-side sessions or refresh-token rotation with logout invalidation
- distributed rate limiting backed by Redis or an API gateway
- transactional outbox for email and CRM side effects
- idempotent real email and CRM provider integrations
- persistent org-scoped AI provider policy in the database or Redis
- audit retention policy, export, and admin filtering
- breached-password and entropy-based password checks
- structured logs shipped to a central service such as Datadog, CloudWatch, or Sentry
- least-privilege deployment secrets and separate keys for API, worker, database, Redis, and LLM provider access

## AI Usage

- The mock provider is deterministic and schema-valid for local development, CI, and demos.
- The frontend shows the active provider, model label, structured-output state, and whether the provider comes from environment config or a runtime override.
- `MOCK_LLM_FAILURE_MODE` supports `none`, `provider_error`, `timeout`, `rate_limit`, `malformed`, and `intermittent`.
- `APPROVAL_WORKER_FAILURE_MODE` supports `none`, `email`, and `crm` for demoing failed processing.
- `APPROVAL_JOB_STALE_AFTER_SECONDS` controls when a `PROCESSING` item with an active job can be recovered through retry processing; the local default is 300 seconds.
- The Anthropic provider uses server-side credentials only.
- Structured output is implemented with forced Anthropic tool use (`tool_choice`) and backend Pydantic validation.
- The UI contract is the persisted `GenerationResult`: draft, decision trace, quality checks, confidence, usage, latency, provider, and model.
- Raw hidden chain-of-thought is not exposed.

## Security Notes

- The browser never receives `ANTHROPIC_API_KEY` or raw provider payloads.
- Mutating backend requests require an allowed `Origin`; the Next.js proxy forwards browser origins and only synthesizes an origin for same-origin browser requests that include `Sec-Fetch-Site: same-origin`.
- API responses include basic security headers such as `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and a restrictive API CSP.
- Lead and CRM fields are treated as untrusted input in the Anthropic prompt. They are JSON-encoded and wrapped in `<lead_profile>` tags with instructions to treat tagged content as data, not model instructions.
- Passwords are capped for bcrypt safety and invalid-login timing is equalized with a dummy hash.
- Role assignment happens on the backend. Clients may request the signup path, but they cannot directly post an arbitrary role.
- Login and signup rate limiting are in-memory and per-process, suitable for the assignment but not a full production limiter.
- Production startup rejects default JWT secrets, insecure auth cookies, and the demo reviewer invite code.

## Test Credentials

- Acme admin: `admin@acme.example` / `AdminPass123!`
- Acme reviewer: `reviewer@acme.example` / `ReviewerPass123!`
- Globex admin: `admin@globex.example` / `AdminPass123!`
- Globex reviewer: `reviewer@globex.example` / `ReviewerPass123!`
- Reviewer signup invite code: `demo-reviewer-code`

## Verification

```bash
cd backend
uv run pytest
uv run ruff check app tests alembic
uv run python -m compileall app tests

cd ../frontend
pnpm lint
pnpm build
pnpm typecheck
```

## Known Limitations

- Email send and CRM sync are simulated; production would integrate real providers through an outbox.
- Stale processing jobs are recoverable through `retry-processing`, but there is no automatic watchdog yet.
- The fake email step runs before fake CRM sync. If this became real side-effect code, it would need idempotent providers or separate outbox-backed jobs to avoid duplicate sends on CRM retry.
- Anthropic startup model validation is available via `ANTHROPIC_VALIDATE_MODEL_ON_STARTUP=true`, but it requires a real API key and model in the environment.
- Frontend API types are hand-written and can drift from backend Pydantic models.
- Idempotency cleanup is not automated yet.
- The local rate limiter does not coordinate across multiple backend processes.
- Worker logs are local rotated files, not centralized structured observability.
- The free deployment runs the API and worker inside one Render web service, so both sleep together on Render's free tier.
- Signup does not verify email ownership yet.
- Reviewer signup uses one demo invite code across organizations. A production version should use per-organization invite records with expiry, single-use consumption, and audit history.
- Signup and organization creation are not written to `audit_logs` yet; the audit trail currently focuses on work-item review and processing actions.
- Signup demo work items are cloned from the local demo scenarios. A production product would create real work from CRM/import events instead.
- Password validation uses length, character-class, and small common-password checks. A production version should use entropy-based scoring and breached-password checks.
- Runtime AI provider switching is disabled by default, process-local, and resets on backend restart. With multiple API workers, an override only affects the process that handled the request; a production version should persist org-scoped provider policy in the database or Redis and fan it out to every worker.

## Future Improvements

- Transactional outbox for email and CRM side effects.
- Background stuck-job monitor or admin recovery action.
- Draft version history with diff and revert.
- Playwright smoke suite.
- Sentry and structured production dashboards.
- Real CRM integration.

## Live URL

Not deployed yet.

## Loom URL

Not recorded yet.
