"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { englishClient } from "@/lib/english/client";
import type { VocabSession } from "@/lib/english/types";
import { emptyVocabReason } from "@/lib/english/view";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { useRoadmap } from "./roadmap-view";
import { TraceNote } from "./trace-note";
import { useLearner } from "./use-learner";

const t = vi.english;

/** Today: vocabulary due, the next milestone, what to learn next (specs/web-english, 1). */
export function EnglishHome() {
  const { roadmap, error, reload } = useRoadmap();
  const { learner } = useLearner();
  const [vocab, setVocab] = useState<VocabSession | null>(null);
  useEffect(() => {
    if (!learner) return;
    let live = true;
    englishClient()
      .vocabSession(learner)
      .then((s) => live && setVocab(s))
      .catch(() => undefined); // the vocabulary card is optional on this page
    return () => {
      live = false;
    };
  }, [learner]);
  const names: Record<string, string> = {};
  roadmap?.milestones.forEach((m) => {
    names[m.slug] = m.name_vi;
    m.hidden.forEach((h) => (names[h.slug] = h.name_vi));
  });
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
      {vocab && (
        <section className="en-card">
          <h2>{t.homeToday.vocabTitle}</h2>
          <p className="en-muted">
            {vocab.due} {t.vocab.due} · {vocab.new_left_today} {t.vocab.newLeft}
          </p>
          {vocab.entries.length > 0 ? (
            <Link className="en-button" href="/tu-vung">
              {t.homeToday.vocabCta}
            </Link>
          ) : (
            <p>
              {emptyVocabReason(vocab.new_left_today) === "done"
                ? t.vocab.empty
                : t.vocab.noMoreWords}
            </p>
          )}
        </section>
      )}
      {roadmap?.level_test && (
        <section className="en-card">
          <h2>{t.homeToday.grammarTitle}</h2>
          <p className="en-muted">{t.home.yourLevel}</p>
          <p className="en-big">
            {t.level.grammar} {roadmap.level_test.grammar_level} ·{" "}
            {t.level.vocab} {roadmap.level_test.vocab_level}
          </p>
          <p className="en-ielts">{roadmap.level_test.ielts_vi}</p>
          {roadmap.learn_next && (
            <div className="en-learn-next">
              <span>{t.home.learnNext}</span>
              <strong>{names[roadmap.learn_next] ?? roadmap.learn_next}</strong>
              <Link
                className="en-button small"
                href={`/on-tap/phan/${roadmap.learn_next}`}
              >
                {t.run.practiseNow}
              </Link>
              {roadmap.learn_next_trace && (
                <TraceNote trace={roadmap.learn_next_trace} names={names} />
              )}
            </div>
          )}
          {roadmap.next_milestone ? (
            <div className="en-learn-next">
              <span>{t.home.nextMilestone}</span>
              <strong>{names[roadmap.next_milestone]}</strong>
              <Link
                className="en-button small"
                href={`/on-tap/cot-moc/${roadmap.next_milestone}`}
              >
                {t.homeToday.nextTest}
              </Link>
            </div>
          ) : (
            <p>{t.home.allKnown}</p>
          )}
          <Link className="en-button secondary" href="/lo-trinh">
            {t.home.openRoadmap}
          </Link>
        </section>
      )}
    </>
  );
}
