"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { englishClient } from "@/lib/english/client";
import type { Roadmap } from "@/lib/english/types";
import { byLevel, percent, showHidden, statusLabel } from "@/lib/english/view";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { TraceNote } from "./trace-note";
import { useLearner } from "./use-learner";

const t = vi.english;

export function useRoadmap(): {
  roadmap: Roadmap | null;
  error: unknown;
  reload: () => void;
} {
  const { learner, error: learnerError, retry } = useLearner();
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!learner) return;
    let live = true;
    englishClient()
      .roadmap(learner)
      .then((r) => {
        if (!live) return;
        setRoadmap(r);
        setError(null);
      })
      .catch((e: unknown) => live && setError(e));
    return () => {
      live = false;
    };
  }, [learner, version]);
  return {
    roadmap,
    error: learnerError ?? error,
    reload: learnerError ? retry : () => setVersion((n) => n + 1),
  };
}

/** Milestones by CEFR level; hidden nodes under a milestone when it needs review or is opened. */
export function RoadmapView() {
  const { roadmap, error, reload } = useRoadmap();
  const [opened, setOpened] = useState<Set<string>>(new Set());
  if (error) return <Problem error={error} onRetry={reload} />;
  if (!roadmap) return <p className="en-muted">{t.loading}</p>;
  const names: Record<string, string> = {};
  roadmap.milestones.forEach((m) => {
    names[m.slug] = m.name_vi;
    m.hidden.forEach((h) => (names[h.slug] = h.name_vi));
  });
  const toggle = (slug: string) =>
    setOpened((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  return (
    <>
      <section className="en-card">
        <h1>{t.roadmap.title}</h1>
        <p className="en-muted">{t.roadmap.subtitle}</p>
        {!roadmap.level_test && (
          <p>
            {t.roadmap.noTest} <Link href="/kiem-tra">{t.nav.levelTest}</Link>
          </p>
        )}
        {roadmap.learn_next && (
          <div className="en-learn-next">
            <span>{t.roadmap.learnNext}</span>
            <strong>{names[roadmap.learn_next] ?? roadmap.learn_next}</strong>
            {roadmap.learn_next_trace && (
              <TraceNote trace={roadmap.learn_next_trace} names={names} />
            )}
          </div>
        )}
      </section>
      {byLevel(roadmap).map(([level, milestones]) => (
        <section key={level} className="en-tier" aria-label={level}>
          <h2>{level}</h2>
          {milestones.map((m) => {
            const isNext = m.slug === roadmap.next_milestone;
            const open = showHidden(m, opened.has(m.slug));
            return (
              <article
                key={m.slug}
                className={`en-milestone is-${m.status}${isNext ? " is-next" : ""}`}
              >
                <div className="en-milestone-top">
                  <strong>{m.name_vi}</strong>
                  <span className="en-status">
                    {statusLabel(m.status, t.roadmap.status)}
                  </span>
                  {isNext && (
                    <span className="en-badge next">{t.roadmap.next}</span>
                  )}
                </div>
                {m.needs.length > 0 && (
                  <p className="en-muted">
                    {t.roadmap.needs}:{" "}
                    {m.needs.map((n) => names[n] ?? n).join(", ")}
                  </p>
                )}
                <button
                  type="button"
                  className="en-link"
                  onClick={() => toggle(m.slug)}
                >
                  {open ? t.roadmap.hide : t.roadmap.show}
                </button>
                {open && (
                  <ul className="en-parts" aria-label={t.roadmap.parts}>
                    {m.hidden.map((h) => (
                      <li key={h.slug} className={h.known ? "is-known" : ""}>
                        <span>{h.name_vi}</span>
                        <span
                          className="en-bar"
                          aria-label={`${percent(h.p_known)}%`}
                        >
                          <span style={{ width: `${percent(h.p_known)}%` }} />
                        </span>
                        <small>{percent(h.p_known)}%</small>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            );
          })}
        </section>
      ))}
      <p className="en-muted">{t.roadmap.practiceSoon}</p>
    </>
  );
}
