import { vi as t } from "@/messages/vi";
import type { Citation, DecisionTrace, PublicItem } from "./contracts";
import { graph } from "./mock";

// UI-only hand-authored fixtures. This is not a P4 golden topic or a verified engine output.
export interface LessonFixture {
  title: string;
  body: string;
  item: PublicItem;
  hints: string[];
  citation: Citation;
}
export function getLessonFixture(slug: string): LessonFixture | null {
  const index = graph.nodes.findIndex((node) => node.slug === slug);
  const content = t.lessonFixtures[index];
  if (!content) return null;
  const chapter = ["02", "01", "02", "05", "05", "07", "03"][index];
  return {
    title: content.title,
    body: content.body,
    item: {
      id: `sample-${slug}`,
      kind: "mcq",
      prompt_vi: content.question,
      options: content.options.map((label) => ({ label })),
    },
    hints: content.hints,
    citation: {
      title: t.sourceBook,
      section: content.section,
      url: `https://allendowney.github.io/ThinkPython/chap${chapter}.html`,
    },
  };
}
export function fixtureTrace(
  slug: string,
  prior: number,
  correct?: boolean,
): DecisionTrace & { prior: number; posterior: number } {
  return {
    kind: correct === undefined ? "next_item" : "bkt_update",
    concept_slug: slug,
    at: new Date().toISOString(),
    prior,
    posterior:
      correct === undefined
        ? prior
        : correct
          ? Math.min(0.98, prior + 0.24)
          : Math.max(0.05, prior - 0.11),
    evidence:
      correct === undefined
        ? {}
        : {
            item_id: `sample-${slug}`,
            correct,
            ...(!correct ? { misconception: "sample-misunderstanding" } : {}),
          },
    rule: correct === undefined ? "sample_selected_concept" : "sample_feedback",
    rule_vi: correct === undefined ? t.flow.mockRule : t.flow.mockUpdate,
    alternatives: graph.nodes
      .filter((n) => n.slug !== slug)
      .slice(0, 2)
      .map((n) => ({
        concept_slug: n.slug,
        p_known: n.p_known,
        why_not_vi: t.flow.mockAlternative,
      })),
  };
}
