"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DataError } from "@/lib/decode";
import { englishClient } from "@/lib/english/client";
import { browserStore } from "@/lib/english/learner";
import type { WritingPrompt } from "@/lib/english/types";
import {
  MAX_CHARS,
  TASK_MIN_WORDS,
  canSubmit,
  consentGiven,
  countWords,
  rememberConsent,
} from "@/lib/english/writing";
import { vi } from "@/messages/vi";
import { Problem, problemText } from "./problem";
import { useLearner } from "./use-learner";
import { promptTypeLabel } from "./writing-home";

const t = vi.english;
const w = t.writing;

export function submitProblem(error: unknown): string {
  if (error instanceof DataError && error.code === "failed") {
    if (error.status === 429) return w.dailyLimit;
    if (error.status === 404) return w.badPrompt;
    if (error.status === 422) return w.rejected;
  }
  return problemText(error);
}

/** The editor: live word count, the consent notice before the first submission. */
export function EssayEditor({ promptId }: { promptId: string }) {
  const router = useRouter();
  const { learner, error: learnerError, retry } = useLearner();
  const [prompt, setPrompt] = useState<WritingPrompt | null | undefined>();
  const [loadError, setLoadError] = useState<unknown>(null);
  const [version, setVersion] = useState(0);
  const [text, setText] = useState("");
  // Read once on the first client render; the page shows "loading" until the learner exists.
  const [consent, setConsent] = useState(() => consentGiven(browserStore()));
  const [askedConsent] = useState(() => !consentGiven(browserStore()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!learner) return;
    let live = true;
    englishClient()
      .writingPrompts(learner)
      .then((ps) => {
        if (!live) return;
        setPrompt(ps.find((p) => p.id === promptId) ?? null);
        setLoadError(null);
      })
      .catch((e: unknown) => live && setLoadError(e));
    return () => {
      live = false;
    };
  }, [learner, promptId, version]);

  if (learnerError) return <Problem error={learnerError} onRetry={retry} />;
  if (loadError)
    return (
      <Problem error={loadError} onRetry={() => setVersion((n) => n + 1)} />
    );
  if (!learner || prompt === undefined)
    return <p className="en-muted">{t.loading}</p>;
  if (prompt === null) return <p className="en-problem">{w.badPrompt}</p>;

  const words = countWords(text);
  const min = TASK_MIN_WORDS[prompt.task];
  const tooLong = text.normalize("NFC").trim().length > MAX_CHARS;

  async function submit() {
    if (!learner || !prompt || busy) return;
    setBusy(true);
    setError(null);
    try {
      rememberConsent(browserStore());
      const id = await englishClient().submitEssay(learner, prompt.id, text);
      router.push(`/bai-viet/${id}`);
    } catch (e: unknown) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <section className="en-card">
      <div className="en-actions">
        <span className="en-badge next">
          {w.task} {prompt.task} · {prompt.level}
        </span>
        <span className="en-muted">{promptTypeLabel(prompt.type)}</span>
        {prompt.status === "draft" && (
          <span className="en-badge">{t.draft}</span>
        )}
      </div>
      <p lang="en" className="en-prompt">
        {prompt.prompt}
      </p>
      <label className="en-essay">
        <span>{w.editor}</span>
        <textarea
          lang="en"
          spellCheck={false}
          value={text}
          placeholder={w.placeholder}
          onChange={(e) => setText(e.target.value)}
          rows={14}
        />
      </label>
      <p className="en-muted" aria-live="polite" data-testid="word-count">
        <strong>{words}</strong> {w.words} ·{" "}
        {words >= min ? w.enough : `${w.atLeast} ${min} ${w.words}`}
      </p>
      {tooLong && <p className="en-problem">{w.tooLong}</p>}
      {askedConsent && (
        <div className="en-consent">
          <strong>{w.consentTitle}</strong>
          <p>{w.consent}</p>
          <label>
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />{" "}
            {w.consentAccept}
          </label>
        </div>
      )}
      {error !== null && (
        <p className="en-problem" role="alert">
          {submitProblem(error)}
        </p>
      )}
      <button
        type="button"
        className="en-button"
        disabled={busy || !canSubmit(text, consent)}
        onClick={submit}
      >
        {busy ? w.sending : w.submit}
      </button>
    </section>
  );
}
