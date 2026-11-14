"use client";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { useRoadmap } from "./roadmap-view";
import { RunView, type RunKind } from "./run-view";

const t = vi.english;

/** Resolves a milestone or hidden-node slug to its name, then shows the run. */
export function RunPage({ kind, slug }: { kind: RunKind; slug: string }) {
  const { roadmap, error, reload } = useRoadmap();
  if (error) return <Problem error={error} onRetry={reload} />;
  if (!roadmap) return <p className="en-muted">{t.loading}</p>;
  const names: Record<string, string> = {};
  roadmap.milestones.forEach((m) => {
    names[m.slug] = m.name_vi;
    m.hidden.forEach((h) => (names[h.slug] = h.name_vi));
  });
  const exists =
    kind === "milestone"
      ? roadmap.milestones.some((m) => m.slug === slug)
      : roadmap.milestones.some((m) => m.hidden.some((h) => h.slug === slug));
  if (!exists) return <p className="en-problem">{t.run.badLink}</p>;
  return <RunView kind={kind} slug={slug} names={names} />;
}
