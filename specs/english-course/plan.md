# Plan: English course skeleton

- `Concept.level: Literal["A1","A2","B1","B2","C1"] | None` in `app/curriculum/course.py` (additive, optional).
  `CourseSpec` checks that no prerequisite has a higher level than its dependent when both have levels.
- `Concept.part_of: Ident | None`; `concept_edges()` returns explicit edges plus hidden node → milestone;
  `part_of_problems()` checks the structure; `CourseSpec.milestones()` and `.hidden_nodes(slug)`; `store.sync_course`
  writes the implicit edges too.
- `app/curriculum/check.py`: `check_course(path) -> Report` (pure: problems and the graph by level and order) and a
  CLI `python -m app.curriculum.check <course.yaml>`. It collects all problems instead of stopping at the first.
- `data/courses/english-ielts.yaml`: a starter roadmap (10 milestones with 19 hidden nodes: tenses, nouns and articles,
  comparison, passive, conditionals), marked in comments as a draft for the owner to extend; one MCQ objective per concept so the file validates.
- `data/sources/english-candidates.yaml`: candidates with url, use, believed licence, `status: to_check`, plus the
  excluded sources with reasons. The fetch adapters come later, only for verified sources.
- Tests: level field optional, level inversion refused, checker reports several problems at once, the starter course
  and the candidates file validate.
