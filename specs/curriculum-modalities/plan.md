# Plan: curriculum-driven modalities and figures

- `apps/api/app/curriculum/figures.py`: figure models (discriminated union on `kind`) with validators.
- `apps/api/app/curriculum/facts.py`: pure ground truth: `chart_facts`, `map_changes`, `process_steps`,
  `diagram_facts`.
- `apps/api/app/curriculum/course.py`: `CourseSpec`, `Objective`, `Rubric`; `load_course(path)`;
  `check_figure(course, objective_id, figure)`.
- `data/courses/`: `python-basics.yaml`, `ielts-academic-writing.yaml`, `statistics-intro.yaml`.
- Tests in `apps/api/tests/curriculum/`; every example course must load.

No database, API or contract change in this slice; nothing calls an LLM. The item contract gains a `figure` field
only in the next spec, together with the web renderer.
