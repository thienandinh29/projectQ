"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import { englishClient, levelResultOf } from "@/lib/english/client";
import {
  LEVELS,
  type Level,
  type LevelResult,
  type Step,
} from "@/lib/english/types";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { QuestionCard } from "./question-card";
import { useLearner } from "./use-learner";

const t = vi.english;
const TARGETS = LEVELS.filter((l) => l !== "A1");

/** The adaptive level test, then its result (specs/web-english, 2). */
export function LevelTest() {
  const { learner, error: learnerError, retry } = useLearner();
  const [target, setTarget] = useState<Level | null>(null);
  const [step, setStep] = useState<Step | null>(null);
  const [result, setResult] = useState<LevelResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(async (action: () => Promise<Step>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setStep(next);
      if (!next.question) setResult(levelResultOf(next));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, []);

  if (learnerError) return <Problem error={learnerError} onRetry={retry} />;
  if (!learner) return <p className="en-muted">{t.loading}</p>;
  const client = englishClient();

  if (result) return <LevelResultView result={result} />;
  if (step?.question && step.run_id) {
    const testId = step.run_id;
    const vocabPart = step.question.item_id.includes("|");
    return (
      <>
        {error != null && <Problem error={error} />}
        <QuestionCard
          key={step.question.item_id}
          question={step.question}
          instruction={vocabPart ? t.level.vocabPart : undefined}
          busy={busy}
          onAnswer={(option) =>
            run(() =>
              client.answerLevelTest(
                learner,
                testId,
                step.question!.item_id,
                option,
              ),
            )
          }
        />
      </>
    );
  }
  return (
    <section className="en-card">
      <h1>{t.level.title}</h1>
      <p>{t.level.intro}</p>
      <fieldset className="en-targets">
        <legend>{t.level.target}</legend>
        {[null, ...TARGETS].map((level) => (
          <label
            key={level ?? "none"}
            className={target === level ? "is-chosen" : ""}
          >
            <input
              type="radio"
              name="target"
              checked={target === level}
              onChange={() => setTarget(level)}
            />
            {level ?? t.level.noTarget}
          </label>
        ))}
      </fieldset>
      {error != null && (
        <Problem error={error} onRetry={() => setError(null)} />
      )}
      <button
        type="button"
        className="en-button"
        disabled={busy}
        onClick={() => run(() => client.startLevelTest(learner, target))}
      >
        {t.level.start}
      </button>
    </section>
  );
}

export function LevelResultView({ result }: { result: LevelResult }) {
  return (
    <section className="en-card en-result">
      <h1>{t.level.resultTitle}</h1>
      <div className="en-levels">
        <div>
          <span>{t.level.grammar}</span>
          <strong>{result.grammar_level}</strong>
        </div>
        <div>
          <span>{t.level.vocab}</span>
          <strong>{result.vocab_level}</strong>
        </div>
      </div>
      <p className="en-ielts">{result.ielts_vi}</p>
      <p className="en-muted">
        {t.level.questions}: {result.questions}
      </p>
      <p className="en-muted">{t.level.estimateNote}</p>
      <Link className="en-button" href="/lo-trinh">
        {t.level.toRoadmap}
      </Link>
    </section>
  );
}
