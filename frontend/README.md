# MealMind frontend

React, TypeScript and Tailwind CSS, built with Create React App. See the [project README](../README.md) for setup, architecture and environment boundaries.

- `npm ci --ignore-scripts`: install lockfile dependencies.
- `npm start`: local development only; bind to loopback with `HOST=127.0.0.1`.
- `npm test -- --watchAll=false --runInBand`: component/client regression suite.
- `node --test scripts/validate-env.test.cjs`: production configuration guards.
- `npm run build`: validated compilation requiring explicit HTTPS public settings.

Only the three public variables in `.env.example` belong in the frontend. Known CRA advisories and CI restrictions are documented in [dependency status](../docs/dependencies.md). Never expose the development server publicly.
