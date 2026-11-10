# Retrieval evaluation sets

One YAML file per topic (`data/eval/<topic>.yaml`): Vietnamese questions, each with the passage(s) a human judged to
answer it. `app/rag/evaluate.py` runs them through the real retriever and reports **hit rate@k**, **recall@k** and
**MRR**. Spec: `specs/retrieval/spec.md` (target: hit rate at k = 5 ≥ 0.8 on golden topic #1).

## Format
```yaml
subject: python-co-ban            # subject slug the retriever searches
questions:
  - id: q01                       # unique
    question_vi: "Khi nào nên dùng elif thay vì if lồng nhau?"
    relevant:                     # every passage that answers it; one match is enough for hit rate
      - source_uri: https://allendowney.github.io/ThinkPython/chap05.html#chained-conditionals
      - contains: "chained conditional"   # optional text snippet; with source_uri, BOTH must match
    note: "optional, for the next reader"
```
Passages are matched by `source_uri` and/or a text snippet (case and diacritics-normalised), never by chunk id:
ids change on every re-index. Find a passage's URI with `select source_uri, section from chunks where content ilike '%…%'`.

## Writing good questions
- **Label before you look at results.** Decide the answer passage from the textbook, then run the evaluation; labelling
  after seeing the retriever's output measures nothing.
- **Write questions the way a learner would**, in Vietnamese, in your own words. Do not copy the textbook's phrases:
  the point is Vietnamese-to-English matching. Mix kinds: definition, "why", "how", "what is the difference".
- **At least 20 questions per topic.** With 10, one question moves the hit rate by 10 points, and the report says so.
- **Keep a held-out half** you never tune against (reranker, chunking); a score you tuned on is optimistic.
- No real learner data, no answers to the quiz items (use the guardrail set for those).

## Run
```bash
cd apps/api
uv run python -m app.rag.evaluate ../../data/eval/<topic>.yaml --min-hit-rate 0.8 --json /tmp/retrieval.json
```
Needs `DATABASE_URL` (the indexed library) and `TEI_URL` (or `--embedder local`). Exit code 1 if hit rate at k = 5 is
below `--min-hit-rate`. The report lists every miss with the top sources returned and, if the right passage was found
below the gate, its rank: a miss at rank 6–10 is what a reranker fixes; a miss that is not retrieved at all is a
chunking or embedding problem.
