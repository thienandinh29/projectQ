import { describe, expect, it, vi } from "vitest";
import { DataError } from "@/lib/decode";
import { COURSE, englishClient, levelResultOf } from "./client";
import { parseQuestion, parseRoadmap, parseStep } from "./decode";
import {
  LEARNER_KEY,
  ensureLearner,
  storedLearner,
  type KeyValueStore,
} from "./learner";
import {
  byLevel,
  emptyVocabReason,
  optionForKey,
  percent,
  progressText,
  showHidden,
} from "./view";

const ID = "0b9d2f4e-1c2a-4d3b-8e5f-6a7b8c9d0e1f";
const trace = {
  kind: "placement_step",
  concept_slug: "comparison",
  at: "2026-11-14T10:00:00Z",
  prior: null,
  posterior: null,
  evidence: {
    item_id: null,
    correct: null,
    misconception: null,
    slip: null,
    guess: null,
  },
  rule: "placement.bayes.ask",
  rule_vi: "Hỏi «So sánh» vì câu trả lời ở đây làm rõ nhất bạn đang ở đâu",
  alternatives: [],
};
const question = {
  item_id: "comparatives-1",
  prompt: "My house is ___ than yours.",
  options: ["the biggest", "biger", "more big", "bigger"],
  draft: true,
  number: 1,
  total: null,
};
const result = {
  grammar_level: "B1",
  vocab_level: "B2",
  ielts_vi: "IELTS khoảng 4.0–5.0 (ước lượng, không phải điểm IELTS)",
  known_milestones: ["present-tenses"],
  questions: 23,
};
const roadmap = {
  course: COURSE,
  level_test: result,
  milestones: [
    {
      slug: "present-tenses",
      name_vi: "Các thì hiện tại",
      level: "A2",
      status: "known",
      needs: [],
      hidden: [
        { slug: "be-present", name_vi: "To be", p_known: 0.9, known: true },
      ],
    },
    {
      slug: "conditional-3",
      name_vi: "Điều kiện loại 3",
      level: "B2",
      status: "partial",
      needs: ["present-tenses"],
      hidden: [
        {
          slug: "third-conditional",
          name_vi: "Loại 3",
          p_known: 0.3,
          known: false,
        },
      ],
    },
    {
      slug: "passive",
      name_vi: "Bị động",
      level: "B1",
      status: "unknown",
      needs: [],
      hidden: [],
    },
  ],
  next_milestone: "passive",
  learn_next: "third-conditional",
  learn_next_trace: { ...trace, kind: "root_cause", prior: 0.3 },
};

describe("decoders", () => {
  it("accept the API's shapes", () => {
    const step = parseStep({
      question,
      run_id: ID,
      kind: "level",
      finished: null,
      traces: [trace],
    });
    expect(step.question?.draft).toBe(true);
    expect(step.question?.total).toBeNull();
    const done = parseStep({
      question: null,
      run_id: ID,
      kind: "level",
      finished: result,
      traces: [],
    });
    expect(levelResultOf(done)?.ielts_vi).toContain("ước lượng");
    const r = parseRoadmap(roadmap);
    expect(r.learn_next_trace?.prior).toBe(0.3);
  });
  it.each([
    [{ ...question, options: ["a"] }],
    [{ ...question, options: ["a", "a"] }],
    [{ ...question, number: -1 }],
    [{ ...question, draft: "yes" }],
  ])("refuse a malformed question %#", (bad) => {
    expect(() => parseQuestion(bad)).toThrow(DataError);
  });
  it("refuse a roadmap with an unknown status, level, probability or next milestone", () => {
    const m = roadmap.milestones[0];
    for (const bad of [
      { ...roadmap, milestones: [{ ...m, status: "great" }] },
      { ...roadmap, milestones: [{ ...m, level: "C2" }] },
      {
        ...roadmap,
        milestones: [{ ...m, hidden: [{ ...m.hidden[0], p_known: 1.5 }] }],
      },
      { ...roadmap, next_milestone: "nowhere" },
    ])
      expect(() => parseRoadmap(bad)).toThrow(DataError);
  });
});

describe("client", () => {
  it("posts through the proxy with the course and returns decoded steps", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          question,
          run_id: ID,
          kind: "level",
          finished: null,
          traces: [],
        }),
      ),
    );
    const step = await englishClient(fetcher).startLevelTest(ID, "B2");
    expect(step.run_id).toBe(ID);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/backend/level-tests");
    expect(JSON.parse(init.body)).toEqual({
      learner_id: ID,
      course: COURSE,
      target: "B2",
    });
    await englishClient(fetcher)
      .answerLevelTest(ID, ID, "comparatives-1", "bigger")
      .catch(() => null);
    expect(fetcher.mock.calls[1][0]).toBe(
      `/api/backend/level-tests/${ID}/answers`,
    );
  });
  it("turns 409 (no reviewed items) and network failures into typed errors", async () => {
    const conflict = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 409 }));
    await expect(
      englishClient(conflict).startLevelTest(ID, null),
    ).rejects.toMatchObject({
      code: "failed",
      status: 409,
    });
    const down = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    await expect(englishClient(down).roadmap(ID)).rejects.toMatchObject({
      code: "network",
    });
    const html = vi.fn().mockResolvedValue(new Response("<html>"));
    await expect(englishClient(html).roadmap(ID)).rejects.toMatchObject({
      code: "contract",
    });
  });
});

describe("learner", () => {
  const memory = (): KeyValueStore & { data: Record<string, string> } => {
    const data: Record<string, string> = {};
    return {
      data,
      getItem: (k) => data[k] ?? null,
      setItem: (k, v) => void (data[k] = v),
    };
  };
  it("is created once, then remembered", async () => {
    const store = memory();
    const create = vi.fn().mockResolvedValue(ID);
    expect(await ensureLearner(store, create)).toBe(ID);
    expect(await ensureLearner(store, create)).toBe(ID);
    expect(create).toHaveBeenCalledTimes(1);
    expect(store.data[LEARNER_KEY]).toBe(ID);
  });
  it("ignores a stored value that is not an id, and survives blocked storage", async () => {
    const store = memory();
    store.data[LEARNER_KEY] = "not-an-id";
    expect(storedLearner(store)).toBeNull();
    const blocked: KeyValueStore = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(await ensureLearner(blocked, async () => ID)).toBe(ID);
  });
});

describe("view helpers", () => {
  it("map keys 1-4 to options and nothing else", () => {
    expect(optionForKey("2", ["a", "b", "c"])).toBe("b");
    expect(optionForKey("4", ["a", "b", "c"])).toBeNull();
    expect(optionForKey("Enter", ["a"])).toBeNull();
  });
  it("group milestones by level, lowest first, skipping empty levels", () => {
    expect(byLevel(parseRoadmap(roadmap)).map(([l]) => l)).toEqual([
      "A2",
      "B1",
      "B2",
    ]);
  });
  it("show hidden nodes when a milestone needs review or is opened", () => {
    const [known, partial] = parseRoadmap(roadmap).milestones;
    expect(showHidden(known, false)).toBe(false);
    expect(showHidden(known, true)).toBe(true);
    expect(showHidden(partial, false)).toBe(true);
  });
  it("word progress without a total for the adaptive test", () => {
    expect(progressText(7, null, "Câu")).toBe("Câu 7");
    expect(progressText(2, 4, "Câu")).toBe("Câu 2/4");
    expect(percent(0.904)).toBe(90);
    expect(percent(1.7)).toBe(100);
  });
  it("say why a vocabulary session is empty", () => {
    expect(emptyVocabReason(0)).toBe("done");
    expect(emptyVocabReason(4)).toBe("noMoreWords");
  });
});
