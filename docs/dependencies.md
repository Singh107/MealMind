# Dependency status

Audit snapshot: September 30, 2026. The repository retains the compatible patched lockfile. No CRA/Vite migration is part of this snapshot.

| Audit | Result |
| --- | --- |
| Declared Python resolution | 18 packages, zero known advisories |
| Patched local Python environment | 36 packages, zero known advisories |
| npm lockfile | 29 findings: 16 high, 4 moderate, 9 low, zero critical |

The npm total includes propagated parent-package findings. Remaining advisories are in CRA/react-scripts build/test/dev-server dependencies: webpack server/middleware, SVG/CSS tooling, serialize-javascript, JSONPath/underscore, SockJS/uuid and Jest/jsdom. These are real advisories, not dismissed as false positives. No React or Supabase browser-runtime package was reported vulnerable in this snapshot; that does not prove the application is vulnerability-free.

Static bundles do not execute the Node development server. Exposed dev servers, untrusted assets and build jobs still face relevant risks. Keep development servers on loopback, review build inputs, isolate jobs and never give untrusted pull requests secrets. CI uses read-only repository permissions, no persisted checkout credentials, no deployment, no `pull_request_target`, no provider keys and no dependency cache.

CI runs `npm audit` as a visibly non-blocking advisory step because known findings remain. Tests/builds remain blocking. Advisory changes must be reviewed; green CI is not a clean vulnerability scan. A supported-toolchain migration is required separately instead of forcing incompatible versions merely to suppress warnings.

Compatible patches reduced npm findings from 34 to 29. Local pip/urllib3 tooling issues were patched. Deploy from a clean environment using declared requirements rather than copying a developer virtual environment. Audit counts change over time; repeat npm and Python audits before release.
