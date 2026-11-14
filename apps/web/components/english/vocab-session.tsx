"use client";
import { useEffect, useState } from "react";
import { englishClient } from "@/lib/english/client";
import type {
  Question,
  VocabAnswer,
  VocabSession as Session,
} from "@/lib/english/types";
import { emptyVocabReason } from "@/lib/english/view";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { QuestionCard } from "./question-card";
import { TraceNote } from "./trace-note";
import { useLearner } from "./use-learner";
import { WordCard } from "./word-card";

const t = vi.english;

/** Today's vocabulary: due words first, new words taught before they are asked (specs/web-english, 5). */
export function VocabSession() {
  const { learner, error: learnerError, retry } = useLearner();
  const [session, setSession] = useState<Session | null>(null);
  const [index, setIndex] = useState(0);
  const [taught, setTaught] = useState(false);
  const [answer, setAnswer] = useState<VocabAnswer | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!learner) return;
    let live = true;
    englishClient()
      .vocabSession(learner)
      .then((s) => {
        if (!live) return;
        setSession(s);
        setIndex(0);
        setTaught(false);
        setAnswer(null);
        setError(null);
      })
      .catch((e: unknown) => live && setError(e));
    return () => {
      live = false;
    };
  }, [learner, version]);

  if (learnerError) return <Problem error={learnerError} onRetry={retry} />;
  if (error && !session)
    return <Problem error={error} onRetry={() => setVersion((n) => n + 1)} />;
  if (!learner || !session) return <p className="en-muted">{t.loading}</p>;

  const entry = session.entries[index];
  const header = (
    <section className="en-card">
      <h1>{t.vocab.title}</h1>
      <p className="en-muted">
        {session.due} {t.vocab.due} · {session.new_left_today} {t.vocab.newLeft}
      </p>
    </section>
  );
  if (!entry)
    return (
      <>
        {header}
        <p className="en-card">
          {session.entries.length
            ? t.vocab.done
            : emptyVocabReason(session.new_left_today) === "done"
              ? t.vocab.empty
              : t.vocab.noMoreWords}
        </p>
      </>
    );

  async function submit(value: string) {
    setBusy(true);
    setError(null);
    try {
      setAnswer(
        await englishClient().vocabAnswer(learner!, entry.item.id, value),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  function next() {
    setIndex((i) => i + 1);
    setTaught(false);
    setAnswer(null);
    setTyped("");
  }

  if (entry.is_new && entry.card && !taught)
    return (
      <>
        {header}
        <section className="en-card">
          <span className="en-badge next">{t.vocab.newWord}</span>
          <WordCard card={entry.card} />
          <button
            type="button"
            className="en-button"
            autoFocus
            onClick={() => setTaught(true)}
          >
            {t.vocab.gotIt}
          </button>
        </section>
      </>
    );

  if (answer)
    return (
      <>
        {header}
        <section className="en-card">
          <div
            className={`en-feedback ${answer.correct ? "is-right" : "is-wrong"}`}
            role="status"
          >
            <strong>{answer.correct ? t.vocab.right : t.vocab.wrong}</strong>
            {!answer.correct && (
              <p>
                {t.vocab.answerWas}: <b lang="en">{answer.accepted}</b>
              </p>
            )}
          </div>
          <WordCard card={answer.card} />
          <p className="en-muted">
            {t.vocab.comesBack}:{" "}
            {new Date(answer.due_at).toLocaleDateString("vi-VN")}
          </p>
          <TraceNote trace={answer.trace} names={{}} />
          <button type="button" className="en-button" autoFocus onClick={next}>
            {t.vocab.next}
          </button>
        </section>
      </>
    );

  const item = entry.item;
  if (item.options) {
    const question: Question = {
      item_id: item.id,
      prompt: item.prompt,
      options: item.options,
      draft: false,
      number: index + 1,
      total: session.entries.length,
    };
    return (
      <>
        {header}
        {error != null && <Problem error={error} />}
        <QuestionCard
          key={item.id}
          question={question}
          instruction={item.instruction_vi}
          busy={busy}
          onAnswer={submit}
        />
      </>
    );
  }
  return (
    <>
      {header}
      {error != null && <Problem error={error} />}
      <form
        className="en-card en-question"
        onSubmit={(e) => {
          e.preventDefault();
          if (typed.trim()) void submit(typed);
        }}
      >
        <p className="en-instruction">{item.instruction_vi}</p>
        <p className="en-prompt" lang="en">
          {item.prompt}
        </p>
        <label className="en-typed">
          <span className="en-muted">
            {t.vocab.hint} “{item.hint}”
          </span>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={t.vocab.typeHere}
            autoFocus
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            lang="en"
            maxLength={100}
            aria-label={t.vocab.typeHere}
          />
        </label>
        <button
          type="submit"
          className="en-button"
          disabled={busy || !typed.trim()}
        >
          {t.submit}
        </button>
      </form>
    </>
  );
}
