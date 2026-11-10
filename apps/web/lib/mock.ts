import { vi } from "@/messages/vi";
import type { DecisionTrace, KnowledgeGraph, PublicItem } from "./contracts";

export const sourceUrl =
  "https://allendowney.github.io/ThinkPython/chap05.html";
const slugs = [
  "variables",
  "data-types",
  "operators",
  "boolean-expressions",
  "conditionals",
  "loops",
  "functions",
];
export const graph: KnowledgeGraph = {
  nodes: slugs.map((slug, i) => ({
    slug,
    name_vi: vi.concepts[i],
    p_known: [0.94, 0.89, 0.82, 0.42, 0.26, 0.12, 0.08][i],
    mastered: i < 3,
  })),
  edges: [
    { from: "variables", to: "data-types" },
    { from: "variables", to: "operators" },
    { from: "data-types", to: "boolean-expressions" },
    { from: "operators", to: "boolean-expressions" },
    { from: "boolean-expressions", to: "conditionals" },
    { from: "conditionals", to: "loops" },
    { from: "conditionals", to: "functions" },
  ],
};
export const item: PublicItem = {
  id: "python-condition-001",
  kind: "mcq",
  prompt_vi: vi.question,
  options: vi.options.map((label) => ({ label })),
};
export const initialTrace: DecisionTrace = {
  kind: "next_item",
  concept_slug: "boolean-expressions",
  at: "2026-11-07T06:00:00Z",
  prior: 0.42,
  evidence: {},
  posterior: 0.42,
  rule: "lowest_unmastered_prerequisite",
  rule_vi: vi.traceRule,
  alternatives: [
    { concept_slug: "operators", p_known: 0.82, why_not_vi: vi.altReason },
  ],
};
// Local simulation only; never use this fixture grader for live learner submissions.
export function mockAttempt(answer: number): {
  correct: boolean;
  trace: DecisionTrace & { prior: number; posterior: number };
} {
  const correct = answer === 1;
  return {
    correct,
    trace: {
      ...initialTrace,
      kind: "bkt_update",
      prior: 0.42,
      posterior: correct ? 0.76 : 0.31,
      evidence: {
        item_id: item.id,
        correct,
        slip: 0.1,
        guess: 0.25,
        ...(!correct ? { misconception: "comparison-confusion" } : {}),
      },
    },
  };
}
