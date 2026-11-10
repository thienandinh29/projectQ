import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getWebConfig } from "./config";
import {
  parseAttempt,
  parseGraph,
  parseHint,
  parsePlacement,
  parseTopic,
  parseTrace,
} from "./decode";

function mock(name: string): unknown {
  return JSON.parse(
    readFileSync(
      resolve(process.cwd(), "../../specs/contracts/mocks", name),
      "utf8",
    ),
  );
}

afterEach(() => vi.unstubAllEnvs());

describe("P1 canonical fixtures consumed by P5", () => {
  it("decodes graph, placement, attempts, hints and topic snapshots", () => {
    expect(
      parseGraph(mock("graph.response.json")).nodes.length,
    ).toBeGreaterThan(0);
    expect(parsePlacement(mock("placement-next.question.json")).done).toBe(
      false,
    );
    expect(parsePlacement(mock("placement-next.done.json")).done).toBe(true);
    expect(parseAttempt(mock("attempts.correct.json")).correct).toBe(true);
    expect(parseAttempt(mock("attempts.wrong.json")).correct).toBe(false);
    expect(
      parseHint(mock("tutor-hint.response.json")).citations.length,
    ).toBeGreaterThan(0);
    expect(parseTopic(mock("topics-id.ready.json")).status).toBe("ready");
  });

  it("preserves null trace probabilities without inventing zero mastery", () => {
    const trace = parseTrace({
      kind: "review",
      concept_slug: "fractions",
      at: "2026-11-07T00:00:00Z",
      prior: null,
      posterior: null,
      rule: "review",
      rule_vi: "Lên lịch ôn tập",
      evidence: { correct: null, slip: null, guess: null },
      alternatives: [],
    });
    expect(trace.prior).toBeNull();
    expect(trace.posterior).toBeNull();
    expect(trace.evidence.correct).toBeNull();
    expect(trace.evidence.slip).toBeNull();
    expect(trace.evidence.guess).toBeNull();
  });

  it("uses the actual integrated upload, answer and hint conventions in API mode", () => {
    vi.stubEnv("NODETRAIL_DATA_MODE", "api");
    vi.stubEnv("NODETRAIL_MAX_UPLOAD_BYTES", "");
    vi.stubEnv("NODETRAIL_UPLOAD_FIELD", "");
    vi.stubEnv("NODETRAIL_ANSWER_ENCODING", "");
    vi.stubEnv("NODETRAIL_HINT_FIRST_LEVEL", "");
    expect(getWebConfig()).toMatchObject({
      uploadMaxBytes: 20_000_000,
      uploadField: "file",
      answerEncoding: "index0",
      hintFirstLevel: 1,
    });
  });
});
