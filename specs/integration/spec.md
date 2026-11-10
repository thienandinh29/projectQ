# Local five-lane integration

User-authorized scope: fetch P1/P2/P3 and integrate with the existing P4 and P5 work.
Use an isolated integration branch. Preserve P4's untracked files before merges;
no force pushes, no shared DB migrations, no fabricated model calls or verified data.

Acceptance: all five histories/data sets present; dependency conflicts resolved;
P4 can consume actual P3 Completion metadata and family-exclusion scope; P4 golden
exports validate against P1; P3 routers mount in P2's app; P5 decodes P1 mocks and
uses canonical request conventions. Tests must distinguish missing DB from code failures.

Not a claim of H7 completion: concrete DB-backed LearningBackend/TopicsBackend/
TutorBackend adapters, worker PipelinePorts, indexed library, credentials and live
content verification are still required. Unconfigured routes return 503, never fixtures.
