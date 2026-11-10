"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { WebConfig } from "@/lib/config";
import { createLearningClient, type DemoScenario } from "@/lib/data-client";
import { graph as sampleGraph } from "@/lib/mock";
import type {
  AttemptResult,
  DecisionTrace,
  HintResult,
  KnowledgeGraph,
  PublicItem,
  ReviewCard,
  TopicRequest,
  TopicSnapshot,
  UploadResult,
  Tier,
} from "@/lib/contracts";
import { DataError } from "@/lib/decode";

export interface LessonState {
  item: PublicItem | null;
  done: boolean;
  traces: DecisionTrace[];
  answer: number | null;
  result: AttemptResult | null;
  hints: HintResult[];
}
const emptyGraph: KnowledgeGraph = { nodes: [], edges: [] };
export function useLearning(config: WebConfig) {
  const client = useMemo(() => createLearningClient(config), [config]);
  const [graph, setGraph] = useState(
    config.mode === "mock" ? sampleGraph : emptyGraph,
  );
  const [selected, setSelected] = useState(
    config.mode === "mock" ? "boolean-expressions" : "",
  );
  const [subject, setSubject] = useState(
    config.mode === "mock" ? "python-sample" : "",
  );
  const [learner, setLearner] = useState(
    config.mode === "mock" ? "demo-learner" : "",
  );
  const [topicId, setTopicId] = useState("");
  const [snapshot, setSnapshot] = useState<TopicSnapshot | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [lessons, setLessons] = useState<Record<string, LessonState>>({});
  const [reviews, setReviews] = useState<ReviewCard[]>([]);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, unknown>>({});
  const [pollVersion, setPollVersion] = useState(0);
  const epoch = useRef(0);
  const locks = useRef(new Set<string>());
  function error(key: string, value: unknown = null) {
    setErrors((all) => ({ ...all, [key]: value }));
  }
  async function run<T>(
    key: string,
    task: () => Promise<T>,
  ): Promise<T | undefined> {
    if (locks.current.has(key)) return;
    locks.current.add(key);
    const version = epoch.current;
    setBusy((all) => ({ ...all, [key]: true }));
    error(key);
    try {
      return await task();
    } catch (caught) {
      if (version === epoch.current) error(key, caught);
    } finally {
      locks.current.delete(key);
      setBusy((all) => ({ ...all, [key]: false }));
    }
  }
  function configureDemo(scenario: DemoScenario) {
    client.configureDemo(scenario);
  }
  async function uploadFile(file: File, consentAccepted: boolean) {
    setUpload(null);
    return run("upload", async () => {
      const received = await client.upload(file, consentAccepted);
      setUpload(received);
      return received;
    });
  }
  function clearUpload() {
    setUpload(null);
    error("upload");
  }
  async function createTopic(input: TopicRequest) {
    return run("create", async () => {
      const id = learner || (await client.learner());
      const result = await client.createTopic(input);
      epoch.current++;
      setLearner(id);
      setTopicId(result.topic_id);
      setSnapshot(null);
      setSubject("");
      setGraph(emptyGraph);
      setSelected("");
      setLessons({});
      setReviews([]);
      setErrors({});
      return result;
    });
  }
  useEffect(() => {
    if (!topicId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      setBusy((all) => ({ ...all, research: true }));
      try {
        const next = await client.topic(topicId, controller.signal);
        if (controller.signal.aborted) return;
        setSnapshot(next);
        setErrors((all) => ({ ...all, research: null }));
        if (next.subject_slug) setSubject(next.subject_slug);
        if (next.status === "failed") {
          setErrors((all) => ({ ...all, research: new DataError("failed") }));
          return;
        }
        if (next.status !== "ready") {
          timer = setTimeout(poll, config.mode === "mock" ? 650 : 2500);
          return;
        }
        if (!next.subject_slug) {
          setErrors((all) => ({ ...all, research: new DataError("contract") }));
          return;
        }
        setBusy((all) => ({ ...all, graph: true }));
        try {
          const result = await client.graph(
            learner,
            next.subject_slug,
            controller.signal,
          );
          if (!controller.signal.aborted) {
            setGraph(result);
            setSelected(
              result.nodes.find((n) => !n.mastered)?.slug ??
                result.nodes[0]?.slug ??
                "",
            );
            setErrors((all) => ({ ...all, graph: null }));
          }
        } catch (caught) {
          if (!controller.signal.aborted)
            setErrors((all) => ({ ...all, graph: caught }));
        } finally {
          if (!controller.signal.aborted)
            setBusy((all) => ({ ...all, graph: false }));
        }
      } catch (caught) {
        if (!controller.signal.aborted)
          setErrors((all) => ({ ...all, research: caught }));
      } finally {
        if (!controller.signal.aborted)
          setBusy((all) => ({ ...all, research: false }));
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [client, config.mode, learner, topicId, pollVersion]);

  async function reloadGraph() {
    if (!subject) {
      error("graph", new DataError("configuration"));
      return;
    }
    await run("graph", async () => {
      const version = epoch.current;
      const result = await client.graph(learner, subject);
      if (version !== epoch.current) return;
      setGraph(result);
      setSelected((slug) =>
        result.nodes.some((node) => node.slug === slug)
          ? slug
          : (result.nodes[0]?.slug ?? ""),
      );
    });
  }
  async function loadLesson(slug = selected, force = false) {
    if (!slug || !subject || (!force && lessons[slug])) return;
    if (
      locks.current.has(`attempt:${slug}`) ||
      locks.current.has(`hint:${slug}`)
    )
      return;
    await run(`lesson:${slug}`, async () => {
      const version = epoch.current;
      const placement = await client.placement(learner, subject, slug);
      if (version !== epoch.current) return;
      const actualSlug =
        config.mode === "mock" ? slug : placement.trace.concept_slug;
      if (!graph.nodes.some((n) => n.slug === actualSlug))
        throw new DataError("contract");
      setLessons((all) => ({
        ...all,
        [actualSlug]: {
          item: placement.item,
          done: placement.done,
          traces: [placement.trace],
          answer: null,
          result: null,
          hints: [],
        },
      }));
      if (config.mode === "api") setSelected(actualSlug);
    });
  }
  function setAnswer(slug: string, answer: number | null) {
    setLessons((all) =>
      all[slug]
        ? { ...all, [slug]: { ...all[slug], answer, result: null } }
        : all,
    );
  }
  async function attempt() {
    const slug = selected;
    const lesson = lessons[slug];
    if (!lesson?.item || lesson.answer === null || lesson.result) return;
    await run(`attempt:${slug}`, async () => {
      const version = epoch.current;
      const result = await client.attempt(
        learner,
        lesson.item!,
        slug,
        lesson.answer!,
        lesson.hints.length,
      );
      if (version !== epoch.current) return;
      setLessons((all) => ({
        ...all,
        [slug]: {
          ...all[slug],
          result,
          traces: [...all[slug].traces, ...result.traces],
        },
      }));
      setGraph((current) => ({
        ...current,
        nodes: current.nodes.map((node) =>
          node.slug === slug
            ? { ...node, p_known: result.p_known, mastered: result.mastered }
            : node,
        ),
      }));
      if (result.correct) await loadReviews();
    });
  }
  async function hint(tier: Tier) {
    const slug = selected;
    const lesson = lessons[slug];
    if (!lesson?.item) return;
    await run(`hint:${slug}`, async () => {
      const version = epoch.current;
      const result = await client.hint(
        learner,
        lesson.item!,
        slug,
        lesson.hints.length,
        tier,
      );
      if (!result.hint_vi.trim()) throw new DataError("failed");
      if (version === epoch.current)
        setLessons((all) => ({
          ...all,
          [slug]: { ...all[slug], hints: [...all[slug].hints, result] },
        }));
    });
  }
  async function loadReviews() {
    await run("reviews", async () => {
      const version = epoch.current;
      const result = await client.reviews(learner);
      if (version === epoch.current) setReviews(result);
    });
  }
  return {
    graph,
    selected,
    setSelected,
    subject,
    topicId,
    snapshot,
    upload,
    lessons,
    reviews,
    busy,
    errors,
    configureDemo,
    uploadFile,
    clearUpload,
    createTopic,
    reloadGraph,
    loadLesson,
    setAnswer,
    attempt,
    hint,
    loadReviews,
    retryResearch: () => setPollVersion((v) => v + 1),
    error,
  };
}
