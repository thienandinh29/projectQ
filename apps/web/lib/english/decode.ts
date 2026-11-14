// Decoders for the English pack: anything malformed is a contract error, never shown as data.
import { DataError, parseTrace, record, string } from "@/lib/decode";
import {
  LEVELS,
  type HiddenNode,
  type Level,
  type LevelResult,
  type Milestone,
  type MilestoneStatus,
  type Question,
  type Roadmap,
  type Step,
} from "./types";

const STATUSES: readonly MilestoneStatus[] = [
  "mastered",
  "known",
  "partial",
  "unknown",
];

function int(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0)
    throw new DataError("contract");
  return value;
}
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") throw new DataError("contract");
  return value;
}
function probability(value: unknown): number {
  if (typeof value !== "number" || !(value >= 0 && value <= 1))
    throw new DataError("contract");
  return value;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new DataError("contract");
  return value;
}
function strings(value: unknown): string[] {
  return array(value).map(string);
}
export function level(value: unknown): Level {
  const v = string(value);
  if (!(LEVELS as readonly string[]).includes(v))
    throw new DataError("contract");
  return v as Level;
}

export function parseQuestion(value: unknown): Question {
  const d = record(value);
  const options = strings(d.options);
  if (options.length < 2 || new Set(options).size !== options.length)
    throw new DataError("contract");
  return {
    item_id: string(d.item_id),
    prompt: string(d.prompt),
    options,
    draft: bool(d.draft),
    number: int(d.number),
    total: d.total === null ? null : int(d.total),
  };
}

export function parseStep(value: unknown): Step {
  const d = record(value);
  return {
    question: d.question === null ? null : parseQuestion(d.question),
    run_id: d.run_id === null ? null : string(d.run_id),
    kind: d.kind === null ? null : string(d.kind),
    finished: d.finished === null ? null : record(d.finished),
    traces: array(d.traces).map(parseTrace),
  };
}

export function parseLevelResult(value: unknown): LevelResult {
  const d = record(value);
  return {
    grammar_level: level(d.grammar_level),
    vocab_level: level(d.vocab_level),
    ielts_vi: string(d.ielts_vi),
    known_milestones: strings(d.known_milestones),
    questions: int(d.questions),
  };
}

function parseHidden(value: unknown): HiddenNode {
  const d = record(value);
  return {
    slug: string(d.slug),
    name_vi: string(d.name_vi),
    p_known: probability(d.p_known),
    known: bool(d.known),
  };
}

function parseMilestone(value: unknown): Milestone {
  const d = record(value);
  const status = string(d.status);
  if (!(STATUSES as readonly string[]).includes(status))
    throw new DataError("contract");
  return {
    slug: string(d.slug),
    name_vi: string(d.name_vi),
    level: level(d.level),
    status: status as MilestoneStatus,
    needs: strings(d.needs),
    hidden: array(d.hidden).map(parseHidden),
  };
}

export function parseRoadmap(value: unknown): Roadmap {
  const d = record(value);
  const milestones = array(d.milestones).map(parseMilestone);
  const slugs = new Set(milestones.map((m) => m.slug));
  const next = d.next_milestone === null ? null : string(d.next_milestone);
  if (next !== null && !slugs.has(next)) throw new DataError("contract");
  return {
    course: string(d.course),
    level_test: d.level_test === null ? null : parseLevelResult(d.level_test),
    milestones,
    next_milestone: next,
    learn_next: d.learn_next === null ? null : string(d.learn_next),
    learn_next_trace:
      d.learn_next_trace === null ? null : parseTrace(d.learn_next_trace),
  };
}
