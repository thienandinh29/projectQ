# Spec: items from cited sources, verified (step 1.3b of `docs/v2/plan-english-pack.md`)

Adds practice items beyond the authored ones, without breaking the rule "no citation, no fact". Starts only when
the owner has verified at least one grammar source's licence (`data/sources/english-candidates.yaml`) and the model
keys are set.

## Embeddings on a GPU notebook
1. The owner's laptop cannot run bge-m3 (measured 14 Nov), so embedding is a batch job elsewhere:
   `python -m app.rag.export <library> chunks.jsonl` writes each chunk with its id and a content hash; a notebook
   (Kaggle or Colab, written by the owner) embeds them with BAAI/bge-m3, normalised, 1024 dimensions, and writes
   `vectors.jsonl`; `python -m app.rag.import_vectors` loads them, refusing a vector whose chunk hash, dimension,
   norm or model name does not match. The model name and revision are recorded with the source.
2. At query time the API embeds only short queries; on a machine without TEI that is the one remaining gap, and the
   plan decides it (a small CPU embedding of queries, or a hosted endpoint) after measuring.

## Generation and verification (the existing gate, applied to English)
3. The generator (DeepSeek, through `app/llm/gateway.py`) writes multiple-choice items for a hidden node from
   retrieved chunks of a verified source, cites the chunk ids, and names a misconception for every distractor.
4. The verifier, a different model family (Gemini), answers each item blind from the cited chunks only
   (`guardrails/answerability.py`). Mismatch or unanswerable → `needs_review`, never served.
5. Items that pass are still `draft` until the owner reviews them; the review queue shows the item, the cited text
   and the verifier's answer.
6. Generated items fill gaps only: the authored bank is used first; generation runs when a hidden node has fewer
   than 2 usable items.

## Gate (from the plan)
7. Verifier catch rate on 50 items with planted errors written by the owner (wrong key, two correct options,
   answer not in the cited text), reported with an exact confidence interval (`evalkit/stats.py`), next to the false
   alarm rate on 50 correct items.

## Not in scope
Reading passages (phase 4), tutor hints for grammar (later), any item without a verified source.
