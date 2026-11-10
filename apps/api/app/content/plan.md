# P4 implementation plan

1. Curate three topics from publisher pages, stable UUID chunk IDs, review checklists.
2. Validate golden files with standard JSON (also valid YAML 1.2) and Pydantic v2.
3. Implement a small adapter around TEAM's complete(task, tier, system, messages,
   schema) interface. Require trusted identity metadata for the actual model used.
4. Generate validated graphs and questions with delimited source data and references.
5. Verify questions blind with a fresh request; fail closed and record hashes/identities.
6. Add reserved SQL 0005, with manual rollback outside the automatic migration glob.
7. Generate, independently verify and release cited Socratic hints without answer keys.
8. Prepare 50 question / 20 hint evaluation cases, empty human labels, JSON metrics.
9. Run focused tests, lint, type checks; document integration gaps and real-model steps.

No new project dependencies, no shared DB writes, no provider calls outside P3.
