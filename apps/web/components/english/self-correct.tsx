"use client";
import { useState } from "react";
import { DataError } from "@/lib/decode";
import { englishClient } from "@/lib/english/client";
import type {
  CorrectionResult,
  CorrectionState,
  GrammarIssue,
} from "@/lib/english/types";
import { vi } from "@/messages/vi";
import { problemText } from "./problem";

const w = vi.english.writing;

/** Hint first, then the answer (specs/writing/step-2.4.md, point 3). No model call. */
export function SelfCorrect({
  learner,
  essayId,
  issue,
  initial,
}: {
  learner: string;
  essayId: string;
  issue: GrammarIssue;
  initial: CorrectionState | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(issue.sentence);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CorrectionResult | null>(null);
  const [error, setError] = useState<unknown>(null);

  if (initial?.accepted && !result)
    return <p className="en-muted">{w.correctedEarlier}</p>;
  if (initial?.answer_shown && !result)
    return <p className="en-muted">{w.answerSeenEarlier}</p>;
  if (!open && !result)
    return (
      <button type="button" className="en-link" onClick={() => setOpen(true)}>
        {w.tryYourself}
      </button>
    );

  async function send(showAnswer: boolean) {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await englishClient().correctSentence(
          learner,
          essayId,
          issue.id,
          showAnswer ? null : text,
          showAnswer,
        ),
      );
    } catch (e: unknown) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const done = result !== null && (result.accepted || result.answer !== null);
  return (
    <div className="en-selfcorrect" data-testid="self-correct">
      {!done && (
        <>
          <p>{w.hint}</p>
          <textarea
            lang="en"
            rows={2}
            value={text}
            spellCheck={false}
            aria-label={w.yourSentence}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="en-actions">
            <button
              type="button"
              className="en-button"
              disabled={busy || !text.trim()}
              onClick={() => send(false)}
            >
              {w.check}
            </button>
            <button
              type="button"
              className="en-link"
              disabled={busy}
              onClick={() => send(true)}
            >
              {w.showAnswer}
            </button>
          </div>
        </>
      )}
      {result && (
        <p role="status" className={result.accepted ? "en-praise" : undefined}>
          {result.feedback_vi}
        </p>
      )}
      {result?.answer && (
        <p>
          {w.answer}: <strong lang="en">{result.answer}</strong>
        </p>
      )}
      {error !== null && (
        <p className="en-problem" role="alert">
          {error instanceof DataError && error.status === 503
            ? w.checkUnavailable
            : problemText(error)}
        </p>
      )}
    </div>
  );
}
