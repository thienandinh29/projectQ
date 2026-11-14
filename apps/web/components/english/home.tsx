"use client";
import Image from "next/image";
import Link from "next/link";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { useRoadmap } from "./roadmap-view";
import { TraceNote } from "./trace-note";

const t = vi.english;

/** Today (minimal in 1.4a): the level test, or the result and where to go next. */
export function EnglishHome() {
  const { roadmap, error, reload } = useRoadmap();
  return (
    <>
      <section className="en-card en-hello">
        <Image src="/sena.svg" width={72} height={72} alt={vi.sena} />
        <div>
          <h1>{t.home.hello}</h1>
          <p className="en-muted">{t.home.senaRule}</p>
        </div>
      </section>
      {error != null && <Problem error={error} onRetry={reload} />}
      {!error && !roadmap && <p className="en-muted">{t.loading}</p>}
      {roadmap && !roadmap.level_test && (
        <section className="en-card">
          <p>{t.home.noTest}</p>
          <Link className="en-button" href="/kiem-tra">
            {t.home.startTest}
          </Link>
        </section>
      )}
      {roadmap?.level_test && (
        <section className="en-card">
          <p className="en-muted">{t.home.yourLevel}</p>
          <p className="en-big">
            {t.level.grammar} {roadmap.level_test.grammar_level} ·{" "}
            {t.level.vocab} {roadmap.level_test.vocab_level}
          </p>
          <p className="en-ielts">{roadmap.level_test.ielts_vi}</p>
          {roadmap.next_milestone ? (
            <p>
              {t.home.nextMilestone}:{" "}
              <strong>
                {
                  roadmap.milestones.find(
                    (m) => m.slug === roadmap.next_milestone,
                  )?.name_vi
                }
              </strong>
            </p>
          ) : (
            <p>{t.home.allKnown}</p>
          )}
          {roadmap.learn_next && roadmap.learn_next_trace && (
            <TraceNote trace={roadmap.learn_next_trace} names={{}} />
          )}
          <Link className="en-button" href="/lo-trinh">
            {t.home.openRoadmap}
          </Link>
        </section>
      )}
    </>
  );
}
