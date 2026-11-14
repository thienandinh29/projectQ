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

export interface Step {
  question: Question | null;
  run_id: string | null;
  kind: string | null;
  finished: Record<string, unknown> | null;
  traces: DecisionTrace[];
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
