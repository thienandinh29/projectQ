# P5 → P2 handoff / pre-break note

ptest integration update (2026-11-07): the P5 branch has been merged into ptest.
See [current integration status](integration-questions.md) for confirmed API settings
and [verification evidence](verification.md) for the current 38-test/build results.
The original implementation-session notes below are retained as historical context;
their statements about a health-only backend or unavailable uv do not describe ptest.

Branch: `p5/web`. All changes are under apps/web; no backend, contracts, root configuration, commit, push or deployment changes. This note is prepared for the agreed H12:00–H13:30 sleep handoff, but **H0/current sprint window is unknown**. It does not claim that the break has started.

## Delivered frontend implementation

Existing forest/ivory/lime workspace preserved; Vietnamese messages, responsive shell, local Sena, accessible Radix dialogs and keyboard focus. Goal validation and asynchronous upload feedback; cancellable research snapshot polling; dagre/React Flow map with zoom/pan/fit, long-label handling, selection and empty/error states; per-node sample lessons, practice, hints, remediation, review cards and trace history; guarded citation links; explicit Free/Pro demo without billing. Session context is retained across navigation, not across page reloads.

Default mock data is hand-authored Python UI data. Topic goals are not genuinely researched, and uploaded files are not parsed/transmitted in mock mode. Mock feedback is not BKT; review dates are not FSRS. No simulated content is substituted into API mode after errors.

## Local commands

From apps/web, Node >=20.9 and pnpm 10.20.0:

```sh
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm start
```

Development: `pnpm dev`. Open `http://localhost:3000`. If Windows has no pnpm on PATH, invoke scripts through `npm.cmd exec --yes --package=pnpm@10.20.0 -- pnpm <script>`. This does not require changing PowerShell execution policy.

## Vercel preparation — P2 deploys

- Root directory: `apps/web`; framework preset: Next.js. Install: `pnpm install --frozen-lockfile`; build: `pnpm build`. Use Next's default output; do not configure static export because the server proxy and runtime config require a server.
- Lockfile: `apps/web/pnpm-lock.yaml`. The tested runtime is Node 25.9.0 on this Windows machine; P2 must validate the selected Vercel-supported runtime. No production URL or environment credentials are provided here.
- Default demo requires no secrets. Set `NODETRAIL_DATA_MODE=mock` explicitly for a demo deployment. Changing server env values may require a new deployment.
- For API mode, configure `NODETRAIL_DATA_MODE=api`, `NODETRAIL_API_URL`, `NODETRAIL_API_KEY`, `NODETRAIL_API_KEY_HEADER`. The URL is server-only. Credentials are used only in the Next proxy and are never serialized to the browser.
- Set `NODETRAIL_UPLOAD_FIELD`, `NODETRAIL_MAX_UPLOAD_BYTES`, `NODETRAIL_ANSWER_ENCODING` (`index0` or `label`) and `NODETRAIL_HINT_FIRST_LEVEL` only after P3 confirms them. Empty values deliberately disable these ambiguous live operations. Copy names from `.env.example`; do not commit actual values.
- The proxy is restricted to documented paths, drops unrelated query parameters, rejects cross-origin POSTs, does not forward browser cookies, does not follow redirects and strips upstream response headers except content type. Upload buffering is bounded by the configured file cap plus multipart overhead; JSON payloads are capped at 64 KiB as a frontend transport limit. Backend and hosting limits still apply.

## Open work / next steps

- No live learning endpoints exist in the current API checkout (`/health` only). API mode is implemented against TEAM.md but unverified. Resolve [integration questions](integration-questions.md), publish OpenAPI and validate real responses before claiming H8 integration.
- Polling provides current state and retry; SSE/heartbeat reconnection is not implemented. No tutor streaming protocol or lesson-content endpoint is invented.
- Browser checks were interrupted by physical Escape; no desktop/mobile end-to-end acceptance can be claimed. Follow [verification checklist](verification.md) before release/recording.
- ffmpeg exists; recorder and script are prepared in demo/. **No video has been recorded.** Do not call it a delivered backup until recorded, replayed and checked.
- API Python checks cannot run through `uv` on the current PATH. No API files changed. P2/P1 should run their required checks in the API environment.
- Missing Spec Kit and shadcn/Figma MCP setup are documented. The spec/plan/tasks were written manually inside the P5-owned folder; no unavailable command or design-frame inspection is claimed.
