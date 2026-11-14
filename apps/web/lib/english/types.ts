// Shapes of the English pack's API responses (apps/api/app/api/grammar.py, vocab.py).
import type { DecisionTrace } from "@/lib/contracts";

export type Level = "A1" | "A2" | "B1" | "B2" | "C1";
export const LEVELS: readonly Level[] = ["A1", "A2", "B1", "B2", "C1"];

export interface Question {
  item_id: string;
  prompt: string;
  options: string[];
  draft: boolean; // shown with a "Bản nháp" badge
  number: number;
  total: number | null; // null for the adaptive level test
}

export interface LevelResult {
  grammar_level: Level;
  vocab_level: Level;
  ielts_vi: string; // shown exactly as the API words it
  known_milestones: string[];
  questions: number;
}

export interface Feedback {
  correct: boolean;
  key: string;
  misconception: string | null;
  misconception_vi: string | null;
}

export interface Step {
  question: Question | null;
  run_id: string | null;
  kind: string | null;
  finished: Record<string, unknown> | null;
  traces: DecisionTrace[];
  feedback: Feedback | null; // runs only: the answer just given
}

export type RunOutcome =
  | {
      kind: "milestone";
      result: "pass" | "gap" | "fail";
      opened: string[];
      learn_next: string | null;
    }
  | { kind: "checks"; learn_next: string | null }
  | { kind: "practice"; node: string; p_known: number; mastered: boolean };

export type VocabKind = "meaning" | "gapfill" | "collocation" | "wordform";

export interface VocabItem {
  id: string;
  kind: VocabKind;
  instruction_vi: string;
  prompt: string;
  options: string[] | null; // multiple choice when set, typed otherwise
  hint: string | null; // first letter, for typed answers
}

export interface WordCard {
  key: string;
  lemma: string;
  pos: string;
  level: string;
  definition: string;
  vi: string | null;
  example: string;
}

export interface VocabEntry {
  item: VocabItem;
  is_new: boolean;
  card: WordCard | null;
  due_at: string | null;
}

export interface VocabSession {
  entries: VocabEntry[];
  due: number;
  new_today: number;
  new_left_today: number;
}

export interface VocabAnswer {
  correct: boolean;
  accepted: string;
  card: WordCard;
  due_at: string;
  trace: DecisionTrace;
}

export type MilestoneStatus = "mastered" | "known" | "partial" | "unknown";

export interface HiddenNode {
  slug: string;
  name_vi: string;
  p_known: number;
  known: boolean;
}

export interface Milestone {
  slug: string;
  name_vi: string;
  level: Level;
  status: MilestoneStatus;
  needs: string[];
  hidden: HiddenNode[];
}

export interface Roadmap {
  course: string;
  level_test: LevelResult | null;
  milestones: Milestone[];
  next_milestone: string | null;
  learn_next: string | null;
  learn_next_trace: DecisionTrace | null;
}

// Writing (specs/writing/step-2.1.md).
export type EssayStatus = "queued" | "analysing" | "done" | "failed";
export const LINKING_GROUPS = [
  "addition",
  "contrast",
  "cause_effect",
  "example",
  "sequence",
  "opinion",
  "conclusion",
] as const;
export type LinkingGroup = (typeof LINKING_GROUPS)[number];

export interface WritingPrompt {
  id: string;
  task: 1 | 2;
  type: string;
  level: Level;
  status: "draft" | "reviewed";
  prompt: string;
}

export interface EssaySummary {
  id: string;
  prompt_id: string;
  status: EssayStatus;
  words: number | null;
  submitted_at: string;
}

/** What plain code measured; no score and no model output in step 2.1. */
export interface EssayResult {
  words: number;
  sentences: number;
  paragraphs: number;
  min_words: number;
  long_enough: boolean;
  avg_sentence_words: number;
  longest_sentence_words: number;
  /** group → phrase → times used */
  linking: Partial<Record<LinkingGroup, Record<string, number>>>;
  linking_groups_used: number;
}

export interface Essay {
  id: string;
  prompt: WritingPrompt | null;
  text: string;
  status: EssayStatus;
  submitted_at: string;
  result: EssayResult | null;
  failure_vi: string | null;
}
