"use client";
import { useEffect, useState } from "react";
import type { Question } from "@/lib/english/types";
import { optionForKey, progressText } from "@/lib/english/view";
import { vi } from "@/messages/vi";

const t = vi.english;

/** One multiple-choice question; keys 1-4 choose, Enter submits (specs/web-english, 10).
 *  Render it with `key={question.item_id}` so the choice resets for each question. */
export function QuestionCard({
  question,
  instruction,
  busy,
  onAnswer,
}: {
  question: Question;
  instruction?: string;
  busy: boolean;
  onAnswer: (option: string) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (busy || event.altKey || event.ctrlKey || event.metaKey) return;
      const option = optionForKey(event.key, question.options);
      if (option) setChosen(option);
      else if (event.key === "Enter" && chosen) onAnswer(chosen);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, chosen, onAnswer, question.options]);
  return (
    <section className="en-card en-question" aria-busy={busy}>
      <div className="en-question-top">
        <span>{progressText(question.number, question.total, t.question)}</span>
        {question.draft && <span className="en-badge">{t.draft}</span>}
      </div>
      <p className="en-instruction">{instruction ?? t.choose}</p>
      <p className="en-prompt" lang="en">
        {question.prompt}
      </p>
      <div className="en-options" role="radiogroup">
        {question.options.map((option, i) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={chosen === option}
            className={`en-option${chosen === option ? " is-chosen" : ""}`}
            disabled={busy}
            onClick={() => setChosen(option)}
            lang="en"
          >
            <kbd>{i + 1}</kbd>
            <span>{option}</span>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="en-button"
        disabled={busy || chosen === null}
        onClick={() => chosen && onAnswer(chosen)}
      >
        {t.submit}
      </button>
      <p className="en-hint">{t.keys}</p>
    </section>
  );
}
