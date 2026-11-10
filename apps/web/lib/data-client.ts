import type {
  AttemptResult,
  HintResult,
  KnowledgeGraph,
  Placement,
  ReviewCard,
  TopicRequest,
  TopicSnapshot,
  UploadResult,
  Tier,
  PublicItem,
} from "./contracts";
import type { WebConfig } from "./config";
import { vi as t } from "@/messages/vi";
import { graph as sampleGraph } from "./mock";
import { fixtureTrace, getLessonFixture } from "./fixtures";
import {
  DataError,
  parseAttempt,
  parseGraph,
  parseHint,
  parsePlacement,
  parseReviews,
  parseTopic,
  parseUpload,
  record,
  string,
} from "./decode";

export type DemoScenario = "normal" | "fail-once" | "empty";
export type DemoOperation =
  "topic" | "upload" | "graph" | "lesson" | "attempt" | "hint" | "reviews";
export interface LearningClient {
  configureDemo(scenario: DemoScenario): void;
  learner(signal?: AbortSignal): Promise<string>;
  upload(
    file: File,
    consentAccepted: boolean,
    signal?: AbortSignal,
  ): Promise<UploadResult>;
  createTopic(
    input: TopicRequest,
    signal?: AbortSignal,
  ): Promise<{ topic_id: string; cached: boolean }>;
  topic(id: string, signal?: AbortSignal): Promise<TopicSnapshot>;
  graph(
    learner: string,
    subject: string,
    signal?: AbortSignal,
  ): Promise<KnowledgeGraph>;
  placement(
    learner: string,
    subject: string,
    slug: string,
    signal?: AbortSignal,
  ): Promise<Placement>;
  attempt(
    learner: string,
    item: PublicItem,
    slug: string,
    answer: number,
    hints: number,
    signal?: AbortSignal,
  ): Promise<AttemptResult>;
  hint(
    learner: string,
    item: PublicItem,
    slug: string,
    level: number,
    tier: Tier,
    signal?: AbortSignal,
  ): Promise<HintResult>;
  reviews(learner: string, signal?: AbortSignal): Promise<ReviewCard[]>;
}

async function wait(signal?: AbortSignal) {
  await new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, 400);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
export function createLearningClient(config: WebConfig): LearningClient {
  if (config.mode === "api") return apiClient(config);
  let scenario: DemoScenario = "normal";
  const failed = new Set<DemoOperation>();
  let graph = structuredClone(sampleGraph);
  const jobs = new Map<string, number>();
  const reviews = new Set<string>();
  let topicSequence = 0;
  async function operation(kind: DemoOperation, signal?: AbortSignal) {
    await wait(signal);
    if (scenario === "fail-once" && !failed.has(kind)) {
      failed.add(kind);
      throw new DataError("network");
    }
  }
  return {
    configureDemo(next) {
      scenario = next;
      failed.clear();
    },
    async learner(signal) {
      await wait(signal);
      return "demo-learner";
    },
    async upload(_file, consentAccepted, signal) {
      if (!consentAccepted) throw new DataError("configuration");
      await operation("upload", signal);
      return { upload_id: "demo-upload", pages: 0, text_ok: true };
    },
    async createTopic(_input, signal) {
      await operation("topic", signal);
      const topic_id = `demo-topic-${++topicSequence}`;
      jobs.set(topic_id, 0);
      graph = structuredClone(sampleGraph);
      reviews.clear();
      return { topic_id, cached: false };
    },
    async topic(id, signal) {
      await operation("topic", signal);
      const current = jobs.get(id);
      if (current === undefined) throw new DataError("failed");
      const step = Math.min(current, 4);
      jobs.set(id, step + 1);
      return {
        status:
          step === 4
            ? "ready"
            : step === 0
              ? "queued"
              : step === 3
                ? "graph"
                : "researching",
        step_vi: step === 4 ? t.flow.researchDone : t.researchSteps[step],
        progress: step / 4,
        subject_slug: "python-sample",
        graph_ready: step >= 3,
        items_ready: step === 4,
        sources:
          step > 0 && scenario !== "empty"
            ? [
                {
                  title: t.sourceBook,
                  publisher: "Green Tea Press",
                  url: "https://allendowney.github.io/ThinkPython/",
                  license: "CC BY-NC-SA 4.0",
                },
              ]
            : [],
        trail:
          scenario === "empty"
            ? []
            : t.researchSteps.slice(0, step).map((text_vi, index) => ({
                at: new Date().toISOString(),
                kind: index === 0 ? "search" : "read",
                text_vi,
              })),
      };
    },
    async graph(_learner, _subject, signal) {
      await operation("graph", signal);
      return scenario === "empty"
        ? { nodes: [], edges: [] }
        : structuredClone(graph);
    },
    async placement(_learner, _subject, slug, signal) {
      await operation("lesson", signal);
      const lesson = getLessonFixture(slug);
      const node = graph.nodes.find((n) => n.slug === slug);
      return {
        item: scenario === "empty" ? null : (lesson?.item ?? null),
        done: scenario === "empty" || !lesson,
        trace: fixtureTrace(slug, node?.p_known ?? 0),
      };
    },
    async attempt(_learner, item, slug, answer, _hints, signal) {
      await operation("attempt", signal);
      if (
        item.id !== `sample-${slug}` ||
        !Number.isInteger(answer) ||
        answer < 0 ||
        answer >= item.options.length
      )
        throw new DataError("contract");
      const node = graph.nodes.find((n) => n.slug === slug);
      if (!node) throw new DataError("contract");
      const correct = answer === 1;
      const trace = fixtureTrace(slug, node.p_known, correct);
      if (trace.posterior === null) throw new DataError("contract");
      node.p_known = trace.posterior;
      node.mastered = node.p_known >= 0.85;
      if (correct) reviews.add(slug);
      const prerequisite = graph.edges.find((edge) => edge.to === slug)?.from;
      return {
        correct,
        p_known: node.p_known,
        mastered: node.mastered,
        traces: [trace],
        ...(!correct && prerequisite
          ? {
              remediation: {
                concept_slug: prerequisite,
                reason_vi: t.flow.mockRemediation,
              },
            }
          : {}),
      };
    },
    async hint(_learner, _item, slug, level, _tier, signal) {
      await operation("hint", signal);
      const lesson = getLessonFixture(slug);
      if (!lesson) throw new DataError("unsupported");
      return {
        hint_vi:
          scenario === "empty" ? "" : (lesson.hints[level] ?? t.hintLimit),
        citations: [lesson.citation],
      };
    },
    async reviews(_learner, signal) {
      await operation("reviews", signal);
      return [...reviews].map((concept_slug) => ({
        concept_slug,
        due_at: new Date().toISOString(),
      }));
    },
  };
}

function apiClient(config: WebConfig): LearningClient {
  const attemptIds = new WeakMap<PublicItem, string>();
  async function request(
    path: string,
    init: RequestInit = {},
  ): Promise<unknown> {
    try {
      const timeout = AbortSignal.timeout(25000);
      const response = await fetch(`/api/backend/${path}`, {
        ...init,
        cache: "no-store",
        signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
      });
      if (!response.ok)
        throw new DataError(
          response.status === 503 ? "configuration" : "failed",
          response.status,
        );
      return await response.json();
    } catch (error) {
      if (
        error instanceof DataError ||
        (error instanceof DOMException && error.name === "AbortError")
      )
        throw error;
      throw new DataError("network");
    }
  }
  const post = (path: string, data: unknown, signal?: AbortSignal) =>
    request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal,
    });
  return {
    configureDemo() {},
    async learner(signal) {
      return string(
        record(await post("learners", { display_name: t.learner }, signal))
          .learner_id,
      );
    },
    async upload(file, consentAccepted, signal) {
      if (!consentAccepted || !config.uploadField || !config.uploadMaxBytes)
        throw new DataError("configuration");
      const form = new FormData();
      form.append(config.uploadField, file);
      return parseUpload(
        await request("uploads", {
          method: "POST",
          body: form,
          headers: { "X-Demo-Upload-Consent": "demo-v1" },
          signal,
        }),
      );
    },
    async createTopic(input, signal) {
      const d = record(await post("topics", input, signal));
      if (typeof d.cached !== "boolean") throw new DataError("contract");
      return { topic_id: string(d.topic_id), cached: d.cached };
    },
    async topic(id, signal) {
      return parseTopic(
        await request(`topics/${encodeURIComponent(id)}`, { signal }),
      );
    },
    async graph(learner_id, subject, signal) {
      return parseGraph(
        await request(`graph?${new URLSearchParams({ learner_id, subject })}`, {
          signal,
        }),
      );
    },
    async placement(learner_id, subject, _slug, signal) {
      return parsePlacement(
        await post("placement/next", { learner_id, subject }, signal),
      );
    },
    async attempt(learner_id, item, _slug, answer, hints_used, signal) {
      if (!config.answerEncoding) throw new DataError("configuration");
      if (!attemptIds.has(item)) attemptIds.set(item, crypto.randomUUID());
      const result = parseAttempt(
        await post(
          "attempts",
          {
            learner_id,
            item_id: item.id,
            client_attempt_id: attemptIds.get(item),
            answer:
              config.answerEncoding === "index0"
                ? answer
                : item.options[answer]?.label,
            hints_used,
          },
          signal,
        ),
      );
      attemptIds.delete(item);
      return result;
    },
    async hint(learner_id, item, _slug, level, tier, signal) {
      if (config.hintFirstLevel === null) throw new DataError("configuration");
      return parseHint(
        await post(
          "tutor/hint",
          {
            learner_id,
            item_id: item.id,
            level: config.hintFirstLevel + level,
            tier,
          },
          signal,
        ),
      );
    },
    async reviews(learner_id, signal) {
      return parseReviews(
        await request(`reviews/due?${new URLSearchParams({ learner_id })}`, {
          signal,
        }),
      );
    },
  };
}
