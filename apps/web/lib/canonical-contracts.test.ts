import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import {
  parseAttempt,
  parseGraph,
  parseHint,
  parsePlacement,
  parseReviews,
  parseTopic,
  parseTrace,
  parseUpload,
} from "./decode";
import { TracePanel } from "../components/trace-panel";

function canonical(name: string): unknown {
  return JSON.parse(
    readFileSync(
      resolve(process.cwd(), "../../specs/contracts/mocks", `${name}.json`),
      "utf8",
    ),
  );
}

describe("P1 canonical contracts", () => {
  it.each([
    ["graph.response", parseGraph],
    ["attempts.correct", parseAttempt],
    ["attempts.wrong", parseAttempt],
    ["placement-next.question", parsePlacement],
    ["placement-next.done", parsePlacement],
    ["topics-id.ready", parseTopic],
    ["topics-id.researching", parseTopic],
    ["uploads.response", parseUpload],
    ["tutor-hint.response", parseHint],
    ["reviews-due.response", parseReviews],
  ] as const)(
    "decodes %s without replacing it with demo data",
    (name, parse) => {
      expect(() => parse(canonical(name))).not.toThrow();
    },
  );

  it("preserves nullable review evidence and never displays a fabricated 0% score", () => {
    const result = parseAttempt(canonical("attempts.correct"));
    const review = result.traces.find((trace) => trace.kind === "review")!;
    expect(review.prior).toBeNull();
    expect(review.posterior).toBeNull();
    expect(review.evidence.slip).toBeNull();
    expect(review.evidence.guess).toBeNull();
    const markup = renderToStaticMarkup(
      createElement(TracePanel, {
        trace: review,
        graph: parseGraph(canonical("graph.response")),
      }),
    );
    expect(markup).toContain(review.rule_vi);
    expect(markup).not.toContain("trace-scores");
    expect(markup).not.toContain("NaN");
  });

  it("accepts omitted nullable fields but still rejects invalid probability evidence", () => {
    const trace = parsePlacement(canonical("placement-next.question")).trace;
    expect(
      parseTrace({ ...trace, prior: null, posterior: null, evidence: {} })
        .prior,
    ).toBeNull();
    expect(() => parseTrace({ ...trace, evidence: { slip: 2 } })).toThrow(
      "contract",
    );
    expect(() => parseTrace({ ...trace, posterior: -1 })).toThrow("contract");
    const withoutProbabilities: Record<string, unknown> = { ...trace };
    delete withoutProbabilities.prior;
    delete withoutProbabilities.posterior;
    expect(parseTrace(withoutProbabilities)).toMatchObject({
      prior: null,
      posterior: null,
    });
  });
});
