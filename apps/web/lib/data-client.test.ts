import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createLearningClient } from "./data-client";
import type { WebConfig } from "./config";
import { parseGraph, parseTrace, parseItem } from "./decode";
import { safeSourceUrl, validateFile } from "./safety";

const config: WebConfig = {
  mode: "mock",
  uploadField: null,
  uploadMaxBytes: 10 * 1024 * 1024,
  answerEncoding: null,
  hintFirstLevel: null,
};
async function finish<T>(promise: Promise<T>) {
  await vi.runAllTimersAsync();
  return promise;
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("quick demo learning journey", () => {
  it("supports upload, research, a selected-node item, remediation, hints, mastery and a review", async () => {
    const client = createLearningClient(config);
    const received = await finish(
      client.upload(new File(["demo"], "syllabus.pdf"), true),
    );
    const created = await finish(
      client.createTopic({
        upload_id: received.upload_id,
        goal_vi: "Python",
        mode: "quick",
        tier: "free",
      }),
    );
    let snapshot = await finish(client.topic(created.topic_id));
    expect(snapshot.status).toBe("queued");
    for (let i = 0; i < 4; i++)
      snapshot = await finish(client.topic(created.topic_id));
    expect(snapshot.status).toBe("ready");
    expect(snapshot.sources.length).toBeGreaterThan(0);
    const graph = await finish(
      client.graph("demo-learner", snapshot.subject_slug!),
    );
    for (const node of graph.nodes) {
      const placement = await finish(
        client.placement("demo-learner", snapshot.subject_slug!, node.slug),
      );
      expect(placement.item?.id).toBe(`sample-${node.slug}`);
      expect(placement.trace.concept_slug).toBe(node.slug);
    }
    const slug = "conditionals";
    const placement = await finish(
      client.placement("demo-learner", snapshot.subject_slug!, slug),
    );
    const wrong = await finish(
      client.attempt("demo-learner", placement.item!, slug, 0, 0),
    );
    expect(wrong.correct).toBe(false);
    expect(
      graph.edges.some(
        (edge) =>
          edge.from === wrong.remediation?.concept_slug && edge.to === slug,
      ),
    ).toBe(true);
    const hint = await finish(
      client.hint("demo-learner", placement.item!, slug, 0, "free"),
    );
    expect(hint.hint_vi).toBeTruthy();
    expect(
      hint.citations.every((citation) => safeSourceUrl(citation.url)),
    ).toBe(true);
    const correct = await finish(
      client.attempt("demo-learner", placement.item!, slug, 1, 1),
    );
    expect(correct.p_known).toBeGreaterThan(wrong.p_known);
    const refreshed = await finish(
      client.graph("demo-learner", snapshot.subject_slug!),
    );
    expect(refreshed.nodes.find((node) => node.slug === slug)?.p_known).toBe(
      correct.p_known,
    );
    expect(await finish(client.reviews("demo-learner"))).toEqual([
      expect.objectContaining({ concept_slug: slug }),
    ]);
  });
  it("retries a failed request without advancing a research job or inventing a result", async () => {
    const client = createLearningClient(config);
    const { topic_id } = await finish(
      client.createTopic({ mode: "quick", tier: "free", goal_vi: "Python" }),
    );
    client.configureDemo("fail-once");
    const failed = expect(client.topic(topic_id)).rejects.toMatchObject({
      code: "network",
    });
    await vi.runAllTimersAsync();
    await failed;
    expect((await finish(client.topic(topic_id))).status).toBe("queued");
    client.configureDemo("empty");
    expect(await finish(client.graph("demo-learner", "python-sample"))).toEqual(
      { nodes: [], edges: [] },
    );
  });
  it("aborts pending mock operations", async () => {
    const controller = new AbortController();
    const client = createLearningClient(config);
    const pending = expect(
      client.topic("irrelevant", controller.signal),
    ).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await pending;
  });
});

describe("live data boundary", () => {
  it("keeps an attempt key on network retry and rotates it only after success", async () => {
    const result = { correct: true, p_known: 0.6, mastered: false, traces: [] };
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("lost response"))
      .mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify(result))),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = createLearningClient({
      ...config,
      mode: "api",
      answerEncoding: "index0",
    });
    const item = {
      id: "i1",
      kind: "mcq" as const,
      prompt_vi: "?",
      options: [{ label: "a" }, { label: "b" }],
    };
    await expect(client.attempt("u1", item, "c", 0, 0)).rejects.toMatchObject({
      code: "network",
    });
    await client.attempt("u1", item, "c", 0, 0);
    await client.attempt("u1", item, "c", 1, 0);
    const bodies = fetchMock.mock.calls.map(([, init]) =>
      JSON.parse(init.body),
    );
    expect(bodies[0].client_attempt_id).toBe(bodies[1].client_attempt_id);
    expect(bodies[2].client_attempt_id).not.toBe(bodies[1].client_attempt_id);
  });
  it("sends an upload only after explicit demo consent", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ upload_id: "u1", pages: 1, text_ok: true }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = createLearningClient({
      ...config,
      mode: "api",
      uploadField: "file",
    });
    const file = new File(["public demo material"], "a.pdf");
    await expect(client.upload(file, false)).rejects.toMatchObject({
      code: "configuration",
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(await client.upload(file, true)).toEqual({
      upload_id: "u1",
      pages: 1,
      text_ok: true,
    });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-Demo-Upload-Consent")).toBe(
      "demo-v1",
    );
  });
  it("rejects malformed data and never substitutes a sample graph", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ nodes: [{ slug: "a" }], edges: [] })),
        ),
    );
    const client = createLearningClient({ ...config, mode: "api" });
    await expect(client.graph("learner", "subject")).rejects.toMatchObject({
      code: "contract",
    });
  });
  it("blocks unknown upload and answer conventions before making a network request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const client = createLearningClient({ ...config, mode: "api" });
    await expect(
      client.upload(new File(["demo"], "a.pdf"), true),
    ).rejects.toMatchObject({ code: "configuration" });
    await expect(
      client.attempt(
        "learner",
        {
          id: "item",
          kind: "mcq",
          prompt_vi: "?",
          options: [{ label: "a" }, { label: "b" }],
        },
        "node",
        0,
        0,
      ),
    ).rejects.toMatchObject({ code: "configuration" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects cycles, dangling edges and invalid probabilities", () => {
    const node = { slug: "a", name_vi: "A", p_known: 0.4, mastered: false };
    expect(() =>
      parseGraph({ nodes: [node], edges: [{ from: "a", to: "unknown" }] }),
    ).toThrow("contract");
    expect(() =>
      parseGraph({
        nodes: [node, { ...node, slug: "b" }],
        edges: [
          { from: "a", to: "b" },
          { from: "b", to: "a" },
        ],
      }),
    ).toThrow("contract");
    expect(() =>
      parseGraph({ nodes: [{ ...node, p_known: 1.2 }], edges: [] }),
    ).toThrow("contract");
    expect(parseGraph({ nodes: [], edges: [] })).toEqual({
      nodes: [],
      edges: [],
    });
  });
  it("retains trace evidence exactly and strips nonpublic item fields", () => {
    const value = {
      kind: "root_cause",
      concept_slug: "a",
      at: "2026-11-07T06:00:00Z",
      prior: 0.7,
      posterior: 0.3,
      evidence: { correct: false, slip: 0, guess: 0.25, item_id: "i" },
      rule: "r",
      rule_vi: "Dữ liệu thật",
      alternatives: [],
    };
    expect(parseTrace(value).evidence).toMatchObject(value.evidence);
    const item = parseItem({
      id: "i",
      kind: "mcq",
      prompt_vi: "?",
      answer: 1,
      options: [
        { label: "a", correct: true },
        { label: "b", correct: false },
      ],
    });
    expect(item).not.toHaveProperty("answer");
    expect(item.options[0]).not.toHaveProperty("correct");
  });
});

describe("source and upload validation", () => {
  it.each([
    "javascript:alert(1)",
    "data:text/html,hi",
    "file:///secret.pdf",
    "//other.example",
    "https://u:p@example.com",
    "not-a-url",
  ])("blocks unsafe source %s", (url) => expect(safeSourceUrl(url)).toBeNull());
  it("preserves section fragments and opens a PDF page only when provided", () => {
    expect(safeSourceUrl("https://example.com/book#section")).toBe(
      "https://example.com/book#section",
    );
    expect(safeSourceUrl("https://example.com/book.pdf?download=1", 5)).toBe(
      "https://example.com/book.pdf?download=1#page=5",
    );
  });
  it("distinguishes unsupported, empty, oversized and unconfigured uploads", () => {
    expect(validateFile({ name: "x.exe", size: 10 }, 100)).toBe("format");
    expect(validateFile({ name: "x.pdf", size: 0 }, 100)).toBe("size");
    expect(validateFile({ name: "x.pdf", size: 101 }, 100)).toBe("size");
    expect(validateFile({ name: "x.pdf", size: 10 }, null)).toBe(
      "unconfigured",
    );
    expect(validateFile({ name: "Đề cương.DOCX", size: 10 }, 100)).toBeNull();
  });
});
