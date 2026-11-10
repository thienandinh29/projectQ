# Implementation plan

Use the agreed Next.js App Router, strict TypeScript, Tailwind, shadcn-style accessible controls, React Flow and dagre stack. Keep Vietnamese UI strings and fixture copy in messages/vi.ts with English secondary strings. Separate contract-shaped types, sample data, mock interactions, graph layout, and presentation components.

Use a warm ivory canvas, dark forest navigation, lime accents, generous whitespace and a lightweight Sena SVG. The main workspace opens on a learning overview with a knowledge map and a focused next step. A modal starts a new topic; research progress leads back to the sample map. All simulated data is visibly labeled.

No Spec Kit CLI/commands or MCP design integrations are installed in this checkout. These local documents capture the requested specify/plan/tasks sequence without claiming those tools ran. Keep them under the owned apps/web path. Backend integration and generated OpenAPI types wait for P1/P2 routes; do not invent API response fields.

Validate with ESLint, tsc, focused graph/mock logic tests and a production build. Follow the manual E2E checklist and inspect the rendered page if browser tooling is available.

## Completion slice

Preserve the existing shell and styles. Extract a contract-shaped asynchronous data client with explicit mock/API configuration. Route live calls through a same-origin server proxy so the shared API key never reaches the browser. Authentication header name, multipart field/limit and answer encoding are not defined in TEAM.md: require P2/P3 configuration, disabling those operations until confirmed. Do not invent a lesson-content route or stream tutor text (only topic SSE is documented). Use topic snapshot polling for recovery; show backend step text rather than assume the unit of `progress`.

Mock mode gets a lesson/question/hint fixture for each graph node, per-node session state, explicit failure/empty scenarios and recoverable async operations. Live mode starts empty and never falls back to sample content after a failure. Render supplied traces verbatim, safe HTTP(S) citation URLs, loading/errors and keyboard-accessible graph selection. Prepare a server-only environment template, Vercel handoff and recording script. No H0 has been provided; do not infer sprint windows or a sleep deadline from wall-clock time.
