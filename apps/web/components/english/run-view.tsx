"use client";
import Link from "next/link";
import { useState } from "react";
import { englishClient } from "@/lib/english/client";
import { parseOutcome } from "@/lib/english/decode";
import type { RunOutcome, Step } from "@/lib/english/types";
import { percent } from "@/lib/english/view";
import { vi } from "@/messages/vi";
import { Feedback } from "./feedback";
import { Problem } from "./problem";
import { QuestionCard } from "./question-card";
import { TraceNote } from "./trace-note";
import { useLearner } from "./use-learner";

const t = vi.english;
export type RunKind = "milestone" | "practice";

/** A milestone test (with the quick checks it may open) or practice on one part. */
export function RunView({
  kind,
  slug,
  names,
}: {
  kind: RunKind;
  slug: string;
  names: Record<string, string>;
}) {
  const name = names[slug] ?? slug;
  const { learner, error: learnerError, retry } = useLearner();
  const [step, setStep] = useState<Step | null>(null);
  const [shown, setShown] = useState<Step | null>(null); // feedback being read before moving on
  const [outcomes, setOutcomes] = useState<RunOutcome[]>([]);
  const [chosen, setChosen] = useState<string | null>(null); // the answer being explained
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (learnerError) return <Problem error={learnerError} onRetry={retry} />;
  if (!learner) return <p className="en-muted">{t.loading}</p>;
  const client = englishClient();

  async function act(action: () => Promise<Step>, answering: boolean) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      if (next.finished) {
        const finishedKind = next.question ? "milestone" : (next.kind ?? kind);
        setOutcomes((o) => [...o, parseOutcome(finishedKind, next.finished!)]);
      }
      if (answering) setShown(next);
      else setStep(next);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const title =
    kind === "milestone" ? t.run.milestoneTitle : t.run.practiceTitle;
  if (!step && !shown)
    return (
      <section className="en-card">
        <h1>
          {title}: {name}
        </h1>
        <p>{t.run.intro}</p>
        {error != null && <Problem error={error} />}
        <button
          type="button"
          className="en-button"
          disabled={busy}
          onClick={() =>
            act(
              () =>
                kind === "milestone"
                  ? client.startMilestoneTest(learner, slug)
                  : client.startPractice(learner, slug),
              false,
            )
          }
        >
          {t.run.start}
        </button>
      </section>
    );

  if (shown) {
    const last = shown.feedback;
    return (
      <section className="en-card">
        {step?.question && (
          <p className="en-prompt" lang="en">
            {step.question.prompt}
          </p>
        )}
        {chosen && (
          <p className="en-muted">
            {t.run.yourAnswer}: <b lang="en">{chosen}</b>
          </p>
        )}
        {last && <Feedback feedback={last} />}
        <Outcomes outcomes={outcomes} traces={shown.traces} names={names} />
        {shown.question ? (
          <button
            type="button"
            className="en-button"
            autoFocus
            onClick={() => {
              setStep(shown);
              setShown(null);
            }}
          >
            {t.run.next}
          </button>
        ) : (
          <Link className="en-button" href="/lo-trinh">
            {t.run.backToRoadmap}
          </Link>
        )}
      </section>
    );
  }

  const current = step!;
  return (
    <>
      {current.kind === "checks" && (
        <p className="en-muted">{t.run.checksTitle}</p>
      )}
      {error != null && <Problem error={error} />}
      {current.question && current.run_id && (
        <QuestionCard
          key={current.question.item_id}
          question={current.question}
          busy={busy}
          onAnswer={(option) => {
            setChosen(option);
            void act(
              () =>
                client.answerRun(
                  learner,
                  current.run_id!,
                  current.question!.item_id,
                  option,
                ),
              true,
            );
          }}
        />
      )}
    </>
  );
}

function Outcomes({
  outcomes,
  traces,
  names,
}: {
  outcomes: RunOutcome[];
  traces: Step["traces"];
  names: Record<string, string>;
}) {
  const last = outcomes.at(-1);
  if (!last) return null;
  const why = traces.find(
    (tr) => tr.kind === "root_cause" || tr.rule.startsWith("milestone."),
  );
  return (
    <div className="en-outcome">
      {last.kind === "milestone" && <p>{t.run[last.result]}</p>}
      {last.kind === "practice" &&
        (last.mastered ? (
          <p className="en-praise">{t.run.mastered}</p>
        ) : (
          <p>
            {t.run.notYet}: {percent(last.p_known)}%. {t.run.notYetNote}
          </p>
        ))}
      {(last.kind === "checks" || last.kind === "milestone") &&
        last.learn_next !== null &&
        last.learn_next !== undefined && (
          <p>
            {t.run.learnNext}:{" "}
            <strong>{names[last.learn_next] ?? last.learn_next}</strong>{" "}
            <Link href={`/on-tap/phan/${last.learn_next}`}>
              {t.run.practiseNow}
            </Link>
          </p>
        )}
      {last.kind === "checks" && last.learn_next === null && (
        <p>{t.run.nothingWeak}</p>
      )}
      {why && <TraceNote trace={why} names={names} />}
    </div>
  );
}
