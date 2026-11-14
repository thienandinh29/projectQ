# Spec: English course (vocabulary and grammar first)

Week 3 of `docs/v2/plan-to-tet-2027.md`. The first real course: English for IELTS, for learners from beginner (about
CEFR A1) to about band 7 (C1). This spec covers the course skeleton (week 3); practice, the level test and the web
flow follow in weeks 4–6 with their own specs.

## Behaviour
1. **Grammar graph.** Each grammar point is a concept with a CEFR level (A1, A2, B1, B2, C1) and prerequisites.
   The graph is a DAG (checked), and a prerequisite is never at a higher level than the point that needs it (checked):
   a B1 point cannot require a B2 point.
2. **Authored and reviewed.** There is no free official syllabus for IELTS, so the graph is drafted by the owner from
   open references and the public CEFR descriptors, and checked by code. It is labelled as authored, not as extracted
   from a textbook.
3. **A checker** prints the graph by level in learning order and reports every problem at once (unknown prerequisite,
   cycle, level inversion, unused concept), so the owner can iterate on the draft without reading Python errors.
4. **Sources are candidates until checked.** `data/sources/english-candidates.yaml` lists the open sources
   considered (word lists, dictionary, example sentences, reading texts, grammar explanations), each with the licence
   it is believed to have and a `status`. Only a source whose licence was read on its own page (`verified`, with the
   date and the page) may be fetched later; NoDerivatives licences are refused; NonCommercial ones are flagged.
   Copyrighted material (Cambridge IELTS books, past papers, English Profile) is listed as excluded, with the reason.
5. The existing Python course is unchanged: `level` is optional.

## Not in scope (week 3)
Fetching or indexing the sources, vocabulary items, grammar items, the level test, the web flow.
