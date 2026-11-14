import { describe, expect, it, vi } from "vitest";
import { DataError } from "@/lib/decode";
import { englishClient, VOCAB_LIST } from "./client";
import {
  parseOutcome,
  parseStep,
  parseVocabAnswer,
  parseVocabSession,
} from "./decode";

const ID = "0b9d2f4e-1c2a-4d3b-8e5f-6a7b8c9d0e1f";
const trace = {
  kind: "review",
  concept_slug: "decision:noun",
  at: "2026-11-14T10:00:00Z",
  prior: null,
  posterior: null,
  evidence: {
    item_id: null,
    correct: false,
    misconception: null,
    slip: null,
    guess: null,
  },
  rule: "review.again",
  rule_vi: "Ôn lại sau 1 ngày",
  alternatives: [],
};
const card = {
  key: "decision:noun",
  lemma: "decision",
  pos: "noun",
  level: "B1",
  definition: "a choice that you make after thinking about the possibilities",
  vi: "quyết định",
  example: "It was a difficult decision to move abroad.",
};
const meaning = {
  id: "core-seed|decision:noun|meaning|0",
  kind: "meaning",
  instruction_vi: "Chọn từ có nghĩa sau:",
  prompt: card.definition,
  options: ["decision", "benefit", "society", "environment"],
  hint: null,
};
const gap = {
  ...meaning,
  id: "core-seed|decision:noun|gapfill|0",
  kind: "gapfill",
  prompt: "It was a difficult ___ to move abroad.",
  options: null,
  hint: "d",
};

describe("run steps and outcomes", () => {
  it("carry feedback with the Vietnamese explanation", () => {
    const step = parseStep({
      question: null,
      run_id: ID,
      kind: "practice",
      traces: [],
      finished: { node: "past-perfect", p_known: 0.948, mastered: false },
      feedback: {
        correct: false,
        key: "had",
        misconception: "present-perfect-for-past-perfect",
        misconception_vi: "Mốc ở quá khứ thì dùng “had”",
      },
    });
    expect(step.feedback?.correct).toBe(false);
    expect(step.feedback?.misconception_vi).toContain("had");
    expect(
      parseStep({
        question: null,
        run_id: ID,
        kind: "level",
        finished: null,
        traces: [],
        feedback: null,
      }).feedback,
    ).toBeNull();
  });
  it("decode each kind of outcome and refuse unknown ones", () => {
    expect(
      parseOutcome("milestone", { result: "gap", opened: ["past-perfect"] }),
    ).toEqual({
      kind: "milestone",
      result: "gap",
      opened: ["past-perfect"],
      learn_next: null,
    });
    expect(parseOutcome("checks", { learn_next: "third-conditional" })).toEqual(
      {
        kind: "checks",
        learn_next: "third-conditional",
      },
    );
    expect(
      parseOutcome("practice", { node: "x", p_known: 0.97, mastered: true }),
    ).toMatchObject({ mastered: true });
    expect(() =>
      parseOutcome("milestone", { result: "great", opened: [] }),
    ).toThrow(DataError);
    expect(() => parseOutcome("level", {})).toThrow(DataError);
  });
});

describe("vocabulary", () => {
  it("decodes a session: new words carry their card, reviews never do", () => {
    const s = parseVocabSession({
      entries: [
        { item: meaning, is_new: true, card, due_at: null },
        {
          item: gap,
          is_new: false,
          card: null,
          due_at: "2026-11-14T00:00:00Z",
        },
      ],
      due: 1,
      new_today: 0,
      new_left_today: 9,
    });
    expect(s.entries[0].card?.vi).toBe("quyết định");
    expect(s.entries[1].item.hint).toBe("d");
    for (const bad of [
      { item: gap, is_new: false, card, due_at: null }, // a review must not show the card
      { item: meaning, is_new: true, card: null, due_at: null }, // a new word must be taught
      {
        item: { ...gap, options: ["a", "b"] },
        is_new: false,
        card: null,
        due_at: null,
      },
      {
        item: { ...meaning, options: null },
        is_new: false,
        card: null,
        due_at: null,
      },
    ])
      expect(() =>
        parseVocabSession({
          entries: [bad],
          due: 0,
          new_today: 0,
          new_left_today: 0,
        }),
      ).toThrow(DataError);
  });
  it("decodes an answer and calls the right routes", async () => {
    const answer = {
      correct: false,
      accepted: "decision",
      card,
      due_at: "2026-11-15T03:00:00Z",
      trace,
    };
    expect(parseVocabAnswer(answer).accepted).toBe("decision");
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            entries: [],
            due: 0,
            new_today: 0,
            new_left_today: 10,
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(answer)));
    const client = englishClient(fetcher);
    await client.vocabSession(ID);
    expect(fetcher.mock.calls[0][0]).toBe(
      `/api/backend/vocab/session?learner_id=${ID}&list=${VOCAB_LIST}`,
    );
    await client.vocabAnswer(ID, gap.id, "decison");
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({
      learner_id: ID,
      item_id: gap.id,
      answer: "decison",
    });
  });
});
