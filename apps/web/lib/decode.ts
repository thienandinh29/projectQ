import type {
  AttemptResult,
  DecisionTrace,
  HintResult,
  KnowledgeGraph,
  Placement,
  PublicItem,
  ReviewCard,
  TopicSnapshot,
  UploadResult,
} from "./contracts";
import { isAcyclic } from "./safety";

export class DataError extends Error {
  constructor(
    public code:
      | "network"
      | "contract"
      | "configuration"
      | "unsupported"
      | "failed"
      | "upload",
    public status?: number,
  ) {
    super(code);
  }
}
export function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new DataError("contract");
  return value as Record<string, unknown>;
}
export function string(value: unknown): string {
  if (typeof value !== "string") throw new DataError("contract");
  return value;
}
function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new DataError("contract");
  return value;
}
function probability(value: unknown): number {
  const n = number(value);
  if (n < 0 || n > 1) throw new DataError("contract");
  return n;
}
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") throw new DataError("contract");
  return value;
}
function list<T>(value: unknown, parse: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) throw new DataError("contract");
  return value.map(parse);
}
function optionalString(value: unknown) {
  return value === undefined || value === null ? undefined : string(value);
}
export function parseGraph(value: unknown): KnowledgeGraph {
  const data = record(value);
  const nodes = list(data.nodes, (value) => {
    const n = record(value);
    return {
      slug: string(n.slug),
      name_vi: string(n.name_vi),
      p_known: probability(n.p_known),
      mastered: bool(n.mastered),
    };
  });
  const slugs = new Set(nodes.map((n) => n.slug));
  if (slugs.size !== nodes.length || nodes.some((n) => !n.slug))
    throw new DataError("contract");
  const edges = list(data.edges, (value) => {
    const e = record(value);
    return { from: string(e.from), to: string(e.to) };
  });
  if (
    edges.some((e) => !slugs.has(e.from) || !slugs.has(e.to) || e.from === e.to)
  )
    throw new DataError("contract");
  const graph = { nodes, edges };
  if (!isAcyclic(graph)) throw new DataError("contract");
  return graph;
}
export function parseTrace(value: unknown): DecisionTrace {
  const data = record(value);
  const evidence = record(data.evidence);
  const kind = string(data.kind);
  if (
    ![
      "bkt_update",
      "placement_step",
      "root_cause",
      "next_item",
      "review",
    ].includes(kind)
  )
    throw new DataError("contract");
  return {
    kind: kind as DecisionTrace["kind"],
    concept_slug: string(data.concept_slug),
    at: string(data.at),
    prior: data.prior == null ? null : probability(data.prior),
    posterior: data.posterior == null ? null : probability(data.posterior),
    rule: string(data.rule),
    rule_vi: string(data.rule_vi),
    evidence: {
      item_id:
        evidence.item_id === null ? null : optionalString(evidence.item_id),
      correct:
        evidence.correct == null ? evidence.correct : bool(evidence.correct),
      misconception:
        evidence.misconception === null
          ? null
          : optionalString(evidence.misconception),
      slip: evidence.slip == null ? evidence.slip : probability(evidence.slip),
      guess:
        evidence.guess == null ? evidence.guess : probability(evidence.guess),
    },
    alternatives: list(data.alternatives, (value) => {
      const a = record(value);
      return {
        concept_slug: string(a.concept_slug),
        p_known: probability(a.p_known),
        why_not_vi: string(a.why_not_vi),
      };
    }),
  };
}
export function parseItem(value: unknown): PublicItem {
  const data = record(value);
  if (data.kind !== "mcq") throw new DataError("contract");
  const options = list(data.options, (value) => ({
    label: string(record(value).label),
  }));
  if (options.length < 2) throw new DataError("contract");
  // Pick only public fields, stripping accidental answer keys from a backend response.
  return {
    id: string(data.id),
    kind: "mcq",
    prompt_vi: string(data.prompt_vi),
    options,
  };
}
export function parseTopic(value: unknown): TopicSnapshot {
  const d = record(value);
  const status = string(d.status);
  if (
    ![
      "queued",
      "researching",
      "indexing",
      "graph",
      "items",
      "ready",
      "failed",
    ].includes(status)
  )
    throw new DataError("contract");
  return {
    status: status as TopicSnapshot["status"],
    step_vi: string(d.step_vi),
    progress: number(d.progress),
    subject_slug: optionalString(d.subject_slug),
    graph_ready: bool(d.graph_ready),
    items_ready: bool(d.items_ready),
    sources: list(d.sources, (value) => {
      const s = record(value);
      return {
        title: string(s.title),
        publisher: string(s.publisher),
        url: string(s.url),
        license: string(s.license),
      };
    }),
    trail: list(d.trail, (value) => {
      const e = record(value);
      const kind = string(e.kind);
      if (!["search", "read", "select"].includes(kind))
        throw new DataError("contract");
      return {
        at: string(e.at),
        kind: kind as "search" | "read" | "select",
        text_vi: string(e.text_vi),
        url: optionalString(e.url),
      };
    }),
  };
}
export function parseUpload(value: unknown): UploadResult {
  const d = record(value);
  return {
    upload_id: string(d.upload_id),
    pages: number(d.pages),
    text_ok: bool(d.text_ok),
  };
}
export function parsePlacement(value: unknown): Placement {
  const d = record(value);
  return {
    item: d.item === null ? null : parseItem(d.item),
    done: bool(d.done),
    gap_slug: optionalString(d.gap_slug),
    trace: parseTrace(d.trace),
  };
}
export function parseAttempt(value: unknown): AttemptResult {
  const d = record(value);
  const r = d.remediation == null ? null : record(d.remediation);
  return {
    correct: bool(d.correct),
    p_known: probability(d.p_known),
    mastered: bool(d.mastered),
    misconception_vi: optionalString(d.misconception_vi),
    remediation: r
      ? { concept_slug: string(r.concept_slug), reason_vi: string(r.reason_vi) }
      : undefined,
    traces: list(d.traces, parseTrace),
  };
}
export function parseHint(value: unknown): HintResult {
  const d = record(value);
  return {
    hint_vi: string(d.hint_vi),
    citations: list(d.citations, (value) => {
      const c = record(value);
      return {
        title: string(c.title),
        section: string(c.section),
        url: string(c.url),
      };
    }),
  };
}
export function parseReviews(value: unknown): ReviewCard[] {
  return list(record(value).cards, (value) => {
    const c = record(value);
    return { concept_slug: string(c.concept_slug), due_at: string(c.due_at) };
  });
}
