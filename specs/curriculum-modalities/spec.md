# Spec: curriculum-driven modalities and figures

**Problem.** Every subject is taught the same way today: generated multiple-choice questions. Python should be
practised by writing code against tests, IELTS Academic Writing by describing a chart or map and writing essays,
mathematics with graphs. And when a lesson needs a picture, an LLM-drawn picture can be wrong, which is worse than
no picture.

**Principle.** The curriculum is the contract. Each course declares which ways of practising (*modalities*) and
which kinds of illustration (*figures*) it uses, per learning objective. The LLM teaches and judges inside that
declaration; it never chooses a modality or figure kind the course does not allow. Figures are structured data,
drawn by code, and every fact an answer depends on is computed from that data by code, never recalled by a model.

## Behaviour
1. A course spec (`data/courses/<slug>.yaml`) declares: the course's allowed modalities and figure kinds; its
   learning objectives, each with one modality, the figure kinds it may use (a subset of the course's), and a
   rubric or tests where the modality needs one; and its rubrics.
2. Modalities: `mcq`, `numeric`, `code`, `short_answer`, `essay`, `figure_description`.
   - `code` needs test cases (or a declared source of them); graded by running them (separate feature).
   - `essay`, `short_answer`, `figure_description` need a rubric; graded by a calibrated LLM judge (separate
     feature), whose agreement with human grades must be measured before it is trusted.
   - `figure_description` needs at least one figure kind.
3. Figure kinds: `chart` (line, bar, pie, table), `map` (a before and an after scene on a grid), `process` (steps),
   `diagram` (nodes and edges), `function_plot` (an expression over a range). Every figure carries Vietnamese alt text.
4. Ground truth by code: for a chart, the key features (maximum and minimum per series, overall change, largest
   single step, ranking at the end); for a map, the change list (added, removed, moved, resized, renamed); for a
   process, the ordered steps; for a diagram, its structure. A grader or judge receives these facts, not an image.
5. A figure is checked against the course: a figure kind the objective does not allow is refused with the reason.
6. Validation is strict: unknown fields, mismatched series lengths, edges to missing nodes, unsafe function
   expressions and empty alt text are refused.

## Done when (this slice)
- Pydantic models for course specs and figures with the validators above, and the pure ground-truth functions,
  covered by unit tests.
- Three example courses that validate: Python (code with tests, diagrams), IELTS Academic Writing (Task 1 chart,
  map and process descriptions; Task 2 essay) and introductory statistics (numeric with charts, MCQ).

## Not in this slice (next specs)
The web renderer (Vega-Lite for charts, SVG templates for maps and processes), the item-contract `figure` field and
its migration, the code sandbox, the rubric judge and its calibration set, function-plot sampling (needs a symbolic
maths dependency), and generating figures with an LLM from a spec template.
