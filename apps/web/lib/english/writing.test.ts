import { describe, expect, it, vi } from "vitest";
import { DataError } from "@/lib/decode";
import { submitProblem } from "@/components/english/essay-editor";
import { bandText, notCountedReason } from "@/components/english/essay-view";
import { englishClient } from "./client";
import { parseEssay, parseEssaySummaries, parseWritingPrompts } from "./decode";
import {
  CONSENT,
  CONSENT_KEY,
  canSubmit,
  consentGiven,
  countWords,
  rememberConsent,
  stillWorking,
} from "./writing";

const ID = "0b9d2f4e-1c2a-4d3b-8e5f-6a7b8c9d0e1f";
const LEARNER = "11111111-2222-4333-8444-555555555555";
const prompt = {
  id: "t2-plastic-ban",
  task: 2,
  type: "opinion",
  level: "B2",
  status: "draft",
  prompt: "Some countries have banned single-use plastic bags. Do you agree?",
};
const result = {
  words: 10,
  sentences: 3,
  paragraphs: 2,
  min_words: 250,
  long_enough: false,
  avg_sentence_words: 3.33,
  longest_sentence_words: 4,
  linking: { contrast: { however: 1 }, conclusion: { "in conclusion": 1 } },
  linking_groups_used: 2,
  note_vi: "ignored by the page",
};
const essay = {
  id: ID,
  prompt,
  text: "Cities are crowded.",
  status: "done",
  submitted_at: "2026-11-20T03:00:00Z",
  result,
  failure_vi: null,
};

function memory(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
  } as Storage;
}

describe("the live word count", () => {
  // The same cases as the API (apps/api/tests/writing/test_analysis.py): the two counts must agree.
  it.each([
    ["I don't think so.", 4],
    ["I don’t think so.", 4],
    ["A well-known fact.", 3],
    ["In 2025, 30% rose.", 4],
    ["— ... !", 0],
    ["", 0],
  ])("%j has %i words", (text, n) => {
    expect(countWords(text)).toBe(n);
  });
});

describe("consent and submission", () => {
  it("asks once per browser and remembers the accepted version", () => {
    const store = memory();
    expect(consentGiven(store)).toBe(false);
    rememberConsent(store);
    expect(store.getItem(CONSENT_KEY)).toBe(CONSENT);
    expect(consentGiven(store)).toBe(true);
    store.setItem(CONSENT_KEY, "writing-v0"); // an older notice is asked again
    expect(consentGiven(store)).toBe(false);
    expect(consentGiven(null)).toBe(false);
  });
  it("needs consent and 1 to 12,000 characters", () => {
    expect(canSubmit("Hello.", true)).toBe(true);
    expect(canSubmit("Hello.", false)).toBe(false);
    expect(canSubmit("   \n", true)).toBe(false);
    expect(canSubmit("a".repeat(12001), true)).toBe(false);
  });
  it("keeps following an essay only while the worker has it", () => {
    expect(
      ["queued", "analysing", "done", "failed"].map((s) =>
        stillWorking(s as "queued"),
      ),
    ).toEqual([true, true, false, false]);
  });
  it("names the daily limit and refusals in Vietnamese", () => {
    expect(submitProblem(new DataError("failed", 429))).toContain("Hôm nay");
    expect(submitProblem(new DataError("failed", 422))).toContain("không nhận");
  });
});

describe("writing decoders", () => {
  it("reads prompts, summaries and an essay", () => {
    expect(parseWritingPrompts([prompt])[0].task).toBe(2);
    const [s] = parseEssaySummaries([
      {
        id: ID,
        prompt_id: prompt.id,
        status: "queued",
        words: null,
        submitted_at: essay.submitted_at,
      },
    ]);
    expect(s.words).toBeNull();
    const e = parseEssay(essay);
    expect(e.result?.linking.contrast).toEqual({ however: 1 });
    expect(
      parseEssay({ ...essay, status: "queued", result: null }).result,
    ).toBeNull();
  });
  it.each([
    ["an unknown status", { ...essay, status: "scored" }],
    ["done without a result", { ...essay, result: null }],
    ["a result before it is done", { ...essay, status: "analysing" }],
    [
      "an unknown linking group",
      { ...essay, result: { ...result, linking: { other: {} } } },
    ],
    ["a negative count", { ...essay, result: { ...result, words: -1 } }],
    ["a bad date", { ...essay, submitted_at: "yesterday" }],
  ])("rejects %s", (_, value) => {
    expect(() => parseEssay(value)).toThrow(DataError);
  });
  it("rejects a prompt for a task that does not exist", () => {
    expect(() => parseWritingPrompts([{ ...prompt, task: 3 }])).toThrow(
      DataError,
    );
  });
});

describe("writing client", () => {
  it("submits with the notice version and deletes with a 204", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ essay_id: ID, status: "queued" }), {
          status: 202,
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = englishClient(fetcher);
    expect(await client.submitEssay(LEARNER, prompt.id, "Text.")).toBe(ID);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/backend/essays");
    expect(JSON.parse(init.body)).toEqual({
      learner_id: LEARNER,
      prompt_id: prompt.id,
      text: "Text.",
      consent: CONSENT,
    });
    await client.deleteEssay(LEARNER, ID);
    expect(fetcher.mock.calls[1][0]).toBe(
      `/api/backend/essays/${ID}?learner_id=${LEARNER}`,
    );
    expect(fetcher.mock.calls[1][1].method).toBe("DELETE");
  });
  it("reports the daily limit as a failure with its status", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 429 }));
    await expect(
      englishClient(fetcher).submitEssay(LEARNER, prompt.id, "x"),
    ).rejects.toMatchObject({ code: "failed", status: 429 });
  });
});

describe("grammar results (step 2.2)", () => {
  const issue = {
    id: 0,
    sentence: "She go to school.",
    sentence_start: 30,
    start: 34,
    end: 36,
    text: "go",
    suggestion: "goes",
    category: "GRAMMAR",
    rule_id: "HE_VERB_AGR",
    message_en: "…",
    errant_type: "R:VERB:SVA",
    node: "present-simple",
    node_vi: "Thì hiện tại đơn",
    explain_vi: "Động từ chưa hợp với chủ ngữ.",
    evidence: true,
    source: "languagetool" as const,
  };
  const v2 = {
    ...result,
    version: 2,
    grammar: { checker: "LanguageTool", issues: [issue], counts: {} },
    grammar_unavailable_vi: null,
    complexity: {
      sentences: 3,
      clauses_per_sentence: 1.33,
      complex_sentence_share: 0.33,
    },
    evidence: [],
  };
  it("reads issues with their marked span and the complexity", () => {
    const r = parseEssay({ ...essay, result: v2 }).result;
    expect(r?.grammar?.issues[0].node_vi).toBe("Thì hiện tại đơn");
    expect(r?.complexity?.clauses_per_sentence).toBe(1.33);
  });
  it("says why an error did not move the roadmap", () => {
    const counted = { ...issue, id: 1 };
    const extra = { ...issue, id: 2, evidence: false };
    const unmapped = { ...issue, id: 3, node: null, evidence: false };
    const why = notCountedReason([counted, extra, unmapped]);
    expect(why(extra)).toContain("tối đa 3");
    expect(why(unmapped)).toContain("chưa gắn");
    expect(notCountedReason([extra])(extra)).toContain("bản nháp");
  });
  it("keeps a step 2.1 result without a grammar section", () => {
    expect(parseEssay(essay).result?.grammar).toBeUndefined();
  });
  it("says why grammar was not checked", () => {
    const r = parseEssay({
      ...essay,
      result: { ...v2, grammar: null, grammar_unavailable_vi: "Chưa kiểm tra" },
    }).result;
    expect(r?.grammar).toBeNull();
    expect(r?.grammarUnavailableVi).toBe("Chưa kiểm tra");
  });
  it.each([
    ["a span that is not in its sentence", { ...issue, text: "goes" }],
    ["a span before its sentence", { ...issue, start: 10, end: 12 }],
    ["evidence without a node", { ...issue, node: null }],
  ])("rejects %s", (_, bad) => {
    expect(() =>
      parseEssay({
        ...essay,
        result: { ...v2, grammar: { issues: [bad] } },
      }),
    ).toThrow(DataError);
  });
});

describe("the band (step 2.3)", () => {
  // the worker writes a band only with the version 2 analysis
  const v2 = {
    ...result,
    version: 2,
    grammar: null,
    grammar_unavailable_vi: "Chưa kiểm tra ngữ pháp",
    complexity: null,
  };
  const band = {
    band_low: 5.5,
    band_high: 6.5,
    uncertain: false,
    model: "m",
    revision: "r",
    status: "draft",
    truncated: false,
    uncertain_reason: null,
  };
  it("is a range, never a point, and 'không chắc' when too wide", () => {
    const r = parseEssay({
      ...essay,
      result: { ...v2, score: band, score_unavailable_vi: null },
    }).result;
    expect(r?.score && bandText(r.score)).toBe("5.5–6.5");
    expect(bandText({ ...band, status: "draft", uncertain: true })).toBe(
      "không chắc",
    );
    expect(
      bandText({ ...band, status: "draft", band_low: 6, band_high: 6 }),
    ).toBe("6.0");
  });
  it("says why there is none, and keeps older results unchanged", () => {
    const r = parseEssay({
      ...essay,
      result: {
        ...v2,
        score: null,
        score_unavailable_vi: "Chưa ước lượng",
      },
    }).result;
    expect(r?.score).toBeNull();
    expect(r?.scoreUnavailableVi).toBe("Chưa ước lượng");
    expect(parseEssay(essay).result?.score).toBeUndefined();
  });
  it.each([
    ["a band off the half steps", { ...band, band_low: 5.3 }],
    ["a reversed range", { ...band, band_low: 7, band_high: 6 }],
    ["an unknown status", { ...band, status: "official" }],
  ])("rejects %s", (_, bad) => {
    expect(() =>
      parseEssay({ ...essay, result: { ...v2, score: bad } }),
    ).toThrow(DataError);
  });
});

const issueBase = {
  id: 0,
  sentence: "She go to school.",
  sentence_start: 0,
  start: 4,
  end: 6,
  text: "go",
  suggestion: "goes",
  category: "AI",
  rule_id: "LLM_CORRECTION",
  message_en: "",
  errant_type: "R:VERB:SVA",
  node: "present-simple",
  node_vi: "Thì hiện tại đơn",
  explain_vi: "Động từ chưa hợp với chủ ngữ.",
};

describe("feedback and self-correction (step 2.4)", () => {
  const v2 = {
    ...result,
    version: 2,
    grammar: null,
    grammar_unavailable_vi: "x",
    complexity: null,
  };
  const point = {
    kind: "issue",
    point_vi: "Câu này cần chia động từ.",
    quotes: ["She go to school"],
  };
  const feedback = {
    criteria: { tr: [point], cc: [], lr: [], gra: [point] },
    dropped: 1,
    quotes_checked: 3,
    quotes_kept: 2,
    model: "deepseek-x",
  };
  it("reads feedback, and says why there is none", () => {
    const r = parseEssay({
      ...essay,
      result: { ...v2, feedback, feedback_unavailable_vi: null },
    }).result;
    expect(r?.feedback?.criteria.tr[0].quotes).toEqual(["She go to school"]);
    expect(r?.feedback?.dropped).toBe(1);
    const none = parseEssay({
      ...essay,
      result: { ...v2, feedback: null, feedback_unavailable_vi: "Chưa có" },
    }).result;
    expect(none?.feedbackUnavailableVi).toBe("Chưa có");
  });
  it.each([
    ["a point without a quote", { ...point, quotes: [] }],
    ["an unknown kind", { ...point, kind: "praise" }],
  ])("rejects %s", (_, bad) => {
    expect(() =>
      parseEssay({
        ...essay,
        result: {
          ...v2,
          feedback: {
            ...feedback,
            criteria: { ...feedback.criteria, tr: [bad] },
          },
        },
      }),
    ).toThrow(DataError);
  });
  it("never lets an AI suggestion count as evidence", () => {
    const ai = { ...issueBase, source: "llm", evidence: true };
    expect(() =>
      parseEssay({
        ...essay,
        result: { ...v2, grammar: { issues: [ai] } },
      }),
    ).toThrow(DataError);
    const fine = { ...issueBase, source: "llm" as const, evidence: false };
    expect(notCountedReason([fine])(fine)).toContain("AI");
  });
  it("reads each error's self-correction state", () => {
    const e = parseEssay({
      ...essay,
      corrections: { "0": { tries: 1, accepted: false, answer_shown: false } },
    });
    expect(e.corrections["0"].tries).toBe(1);
    expect(parseEssay(essay).corrections).toEqual({});
  });
  it("posts a try, or asks for the answer", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          accepted: true,
          tries: 1,
          answer: "She goes.",
          feedback_vi: "Đúng rồi!",
        }),
      ),
    );
    const out = await englishClient(fetcher).correctSentence(
      LEARNER,
      ID,
      0,
      "She goes.",
    );
    expect(out.accepted).toBe(true);
    expect(fetcher.mock.calls[0][0]).toBe(
      `/api/backend/essays/${ID}/corrections`,
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      learner_id: LEARNER,
      issue_id: 0,
      sentence: "She goes.",
      show_answer: false,
    });
  });
});
