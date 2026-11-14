// Decoders for the English pack: anything malformed is a contract error, never shown as data.
import { DataError, parseTrace, record, string } from "@/lib/decode";
import {
  LEVELS,
  LINKING_GROUPS,
  type Essay,
  type EssayResult,
  type EssayStatus,
  type EssaySummary,
  type LinkingGroup,
  type WritingPrompt,
  type Feedback,
  type HiddenNode,
  type Level,
  type LevelResult,
  type Milestone,
  type MilestoneStatus,
  type Question,
  type Roadmap,
  type RunOutcome,
  type Step,
  type VocabAnswer,
  type VocabEntry,
  type VocabItem,
  type VocabKind,
  type VocabSession,
  type WordCard,
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

function optionalString(value: unknown): string | null {
  return value === null || value === undefined ? null : string(value);
}

function parseFeedback(value: unknown): Feedback | null {
  if (value === null || value === undefined) return null;
  const d = record(value);
  return {
    correct: bool(d.correct),
    key: string(d.key),
    misconception: optionalString(d.misconception),
    misconception_vi: optionalString(d.misconception_vi),
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
    feedback: parseFeedback(d.feedback),
  };
}

/** The outcome of a finished milestone test, quick checks or practice run. */
export function parseOutcome(
  kind: string,
  value: Record<string, unknown>,
): RunOutcome {
  const learnNext = optionalString(value.learn_next);
  if (kind === "milestone") {
    const result = string(value.result);
    if (!["pass", "gap", "fail"].includes(result))
      throw new DataError("contract");
    return {
      kind,
      result: result as "pass" | "gap" | "fail",
      opened: strings(value.opened),
      learn_next: learnNext,
    };
  }
  if (kind === "checks") return { kind, learn_next: learnNext };
  if (kind === "practice")
    return {
      kind,
      node: string(value.node),
      p_known: probability(value.p_known),
      mastered: bool(value.mastered),
    };
  throw new DataError("contract");
}

const VOCAB_KINDS: readonly VocabKind[] = [
  "meaning",
  "gapfill",
  "collocation",
  "wordform",
];

function parseVocabItem(value: unknown): VocabItem {
  const d = record(value);
  const kind = string(d.kind);
  if (!(VOCAB_KINDS as readonly string[]).includes(kind))
    throw new DataError("contract");
  const options = d.options === null ? null : strings(d.options);
  if ((kind === "meaning") !== (options !== null))
    throw new DataError("contract");
  return {
    id: string(d.id),
    kind: kind as VocabKind,
    instruction_vi: string(d.instruction_vi),
    prompt: string(d.prompt),
    options,
    hint: optionalString(d.hint),
  };
}

export function parseWordCard(value: unknown): WordCard {
  const d = record(value);
  return {
    key: string(d.key),
    lemma: string(d.lemma),
    pos: string(d.pos),
    level: string(d.level),
    definition: string(d.definition),
    vi: optionalString(d.vi),
    example: string(d.example),
  };
}

function parseVocabEntry(value: unknown): VocabEntry {
  const d = record(value);
  const isNew = bool(d.is_new);
  const card = d.card === null ? null : parseWordCard(d.card);
  if (isNew !== (card !== null)) throw new DataError("contract"); // reviews never show the card
  return {
    item: parseVocabItem(d.item),
    is_new: isNew,
    card,
    due_at: optionalString(d.due_at),
  };
}

export function parseVocabSession(value: unknown): VocabSession {
  const d = record(value);
  return {
    entries: array(d.entries).map(parseVocabEntry),
    due: int(d.due),
    new_today: int(d.new_today),
    new_left_today: int(d.new_left_today),
  };
}

export function parseVocabAnswer(value: unknown): VocabAnswer {
  const d = record(value);
  return {
    correct: bool(d.correct),
    accepted: string(d.accepted),
    card: parseWordCard(d.card),
    due_at: string(d.due_at),
    trace: parseTrace(d.trace),
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

// Writing (specs/writing/step-2.1.md).
const ESSAY_STATUSES: readonly EssayStatus[] = [
  "queued",
  "analysing",
  "done",
  "failed",
];

function essayStatus(value: unknown): EssayStatus {
  const v = string(value);
  if (!(ESSAY_STATUSES as readonly string[]).includes(v))
    throw new DataError("contract");
  return v as EssayStatus;
}

function timestamp(value: unknown): string {
  const v = string(value);
  if (Number.isNaN(Date.parse(v))) throw new DataError("contract");
  return v;
}

function nonNegative(value: unknown): number {
  if (typeof value !== "number" || !(value >= 0))
    throw new DataError("contract");
  return value;
}

export function parseWritingPrompt(value: unknown): WritingPrompt {
  const d = record(value);
  const status = string(d.status);
  if (d.task !== 1 && d.task !== 2) throw new DataError("contract");
  if (status !== "draft" && status !== "reviewed")
    throw new DataError("contract");
  return {
    id: string(d.id),
    task: d.task,
    type: string(d.type),
    level: level(d.level),
    status,
    prompt: string(d.prompt),
  };
}

export function parseWritingPrompts(value: unknown): WritingPrompt[] {
  return array(value).map(parseWritingPrompt);
}

export function parseEssaySummaries(value: unknown): EssaySummary[] {
  return array(value).map((v) => {
    const d = record(v);
    return {
      id: string(d.id),
      prompt_id: string(d.prompt_id),
      status: essayStatus(d.status),
      words: d.words === null ? null : int(d.words),
      submitted_at: timestamp(d.submitted_at),
    };
  });
}

function parseLinking(value: unknown): EssayResult["linking"] {
  const d = record(value);
  const out: EssayResult["linking"] = {};
  for (const [group, phrases] of Object.entries(d)) {
    if (!(LINKING_GROUPS as readonly string[]).includes(group))
      throw new DataError("contract");
    const counts: Record<string, number> = {};
    for (const [phrase, n] of Object.entries(record(phrases)))
      counts[phrase] = int(n);
    out[group as LinkingGroup] = counts;
  }
  return out;
}

export function parseEssayResult(value: unknown): EssayResult {
  const d = record(value);
  return {
    words: int(d.words),
    sentences: int(d.sentences),
    paragraphs: int(d.paragraphs),
    min_words: int(d.min_words),
    long_enough: bool(d.long_enough),
    avg_sentence_words: nonNegative(d.avg_sentence_words),
    longest_sentence_words: int(d.longest_sentence_words),
    linking: parseLinking(d.linking),
    linking_groups_used: int(d.linking_groups_used),
  };
}

export function parseEssay(value: unknown): Essay {
  const d = record(value);
  const status = essayStatus(d.status);
  const result = d.result === null ? null : parseEssayResult(d.result);
  if ((status === "done") !== (result !== null))
    throw new DataError("contract");
  return {
    id: string(d.id),
    prompt: d.prompt === null ? null : parseWritingPrompt(d.prompt),
    text: string(d.text),
    status,
    submitted_at: timestamp(d.submitted_at),
    result,
    failure_vi: optionalString(d.failure_vi),
  };
}
