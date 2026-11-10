import { describe, expect, it } from "vitest";
import { graph, item, mockAttempt } from "./mock";

describe("mock learning boundary", () => {
  it("does not expose correctness in the public item", () => {
    expect(
      item.options.every((option) => Object.keys(option).join() === "label"),
    ).toBe(true);
    expect(item).not.toHaveProperty("answer");
  });
  it("returns a trace for both feedback branches", () => {
    const wrong = mockAttempt(0);
    const correct = mockAttempt(1);
    expect(wrong.correct).toBe(false);
    expect(wrong.trace.evidence.misconception).toBeTruthy();
    expect(wrong.trace.prior).not.toBeNull();
    expect(wrong.trace.posterior).toBeLessThan(wrong.trace.prior!);
    expect(correct.correct).toBe(true);
    expect(correct.trace.prior).not.toBeNull();
    expect(correct.trace.posterior).toBeGreaterThan(correct.trace.prior!);
    expect(correct.trace.evidence.misconception).toBeUndefined();
  });
  it("references existing concepts in every prerequisite and trace", () => {
    const slugs = new Set(graph.nodes.map((node) => node.slug));
    for (const edge of graph.edges) {
      expect(slugs.has(edge.from)).toBe(true);
      expect(slugs.has(edge.to)).toBe(true);
    }
    expect(slugs.has(mockAttempt(0).trace.concept_slug)).toBe(true);
  });
});
