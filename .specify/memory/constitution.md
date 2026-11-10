# Project constitution

Engine code remains pure and tested; every engine decision returns a trace. LLM access goes only through the
gateway, and generated content is cited and verified by a different model family before it is served. Never read
secrets or commit credentials. Vietnamese product messages, English code/docs, UTF-8. New modules require
spec/plan/tasks before code. Keep tests isolated from development data. Never present fixtures or sample data as
real research or real results. Require pytest, ruff and mypy. Do not push without the owner's instruction.
