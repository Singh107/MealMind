# Security and deployment requirements

MealMind separates AI proposals, deterministic checks and account authority. This describes implemented boundaries and release requirements, not a penetration-test certification.

## Secrets and accounts

Gemini/USDA secrets remain server-side. The browser gets only public API/Supabase configuration. A publishable/anon key is intentionally public, not a substitute for RLS. Backend identity is verified with Supabase Auth rather than decoded unverified claims or a submitted owner ID. Ordinary repositories use caller JWTs and owner filters, never service-role credentials.

Migrations enable/force RLS on profiles, saved_recipes, user_preferences and pantry_items, with owner checks for every CRUD operation. Fresh deployed policy and two-user checks remain deployment responsibilities. Browser sessions use the existing Supabase storage model; XSS defenses and CSP matter.

Local environment files, verification credentials, logs and backups stay ignored. `tools/scan_staged.py` scans Git index contents; known environment values are compared in memory when available. Pattern scanning cannot prove absence of every secret or private detail.

## Application controls

- Strict production settings reject mocks, missing configuration, wildcard/local hosts, invalid CORS origins and privileged Supabase key types. Configuration errors suppress input values.
- The production target `app.main:create_production_app --factory` refuses development mode. Debug and production API docs are disabled.
- Strict schemas, safe errors and React text escaping retain structured boundaries. AI nutrition/safety statements are not authoritative.
- Ordinary bodies are capped at 2 MiB + 64 KiB; image bodies at 5 MiB; uploads have a 15-second deadline. Actual chunks and declared sizes are checked.
- JPEG/PNG/WebP images must pass decoded-format validation and a 16-million-pixel limit. Animated/corrupt files are rejected; fresh encoding removes original metadata. No permanent image storage.
- Gemini/USDA response buffers are capped at 4 MiB decoded content. Deadlines, bounded repair/retry behavior and lookup concurrency remain.
- Default per-process admission: 120 units/minute per peer, 10 expensive units/minute per peer, 60 global expensive units/minute, 500/day-window and four concurrent expensive workflows. Repair costs two units. Rejection is HTTP 429 with Retry-After.

These are not billing guarantees. Processes/restarts reset or multiply limits; shared IPs share an allowance. Account lists aggregate saved recipes and need storage/capacity review. The provider buffer cap does not cover every Supabase response or transient transport allocation.

## Logs, headers and deployment gates

Application logs retain trace IDs, exception types and allowlisted provider statuses, not raw bodies, passwords, photos or provider output. HTTP client INFO/DEBUG logging is disabled because USDA uses a credential query parameter. Host/APM logs must also redact sensitive headers/queries/bodies.

API middleware sends nosniff, no-referrer, frame denial and no-store headers. The frontend host needs its own tested CSP, frame-ancestors/object restrictions, exact connect/script sources and Permissions-Policy. Consider Google font/image origins and local blob previews explicitly. Inline runtime scripts require a build hash or disabled runtime inlining. Validate report-only CSP before enforcement. HSTS belongs only on validated production HTTPS, never localhost.

Before public deployment:

1. Use managed secrets and explicit HTTPS public origins; rebuild with real public configuration. CI placeholder builds are not deployable.
2. Trust only controlled proxies which strip spoofed forwarding headers, or disable proxy headers for direct traffic.
3. Apply shared edge/connection/header/body limits, provider quotas, account storage quotas and monitoring.
4. Verify actual RLS, Supabase Site URL and narrow recovery redirects; test account isolation/recovery/session restoration under deployed headers.
5. Review [toolchain advisories](dependencies.md), isolate reviewed builds and never expose CRA's development server. Resolve or explicitly gate remaining risks before hosting/CI use.
6. Confirm asset rights, privacy disclosures, retention and a vulnerability-reporting contact through owner decisions.

No production infrastructure, DNS, dashboard configuration or deployment is provided here.
