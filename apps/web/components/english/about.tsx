"use client";
import { useState } from "react";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { useLearner } from "./use-learner";

const t = vi.english.about;

/** The learner id (for DRAFT_ITEM_LEARNERS) and what the numbers mean (specs/web-english, 6). */
export function About() {
  const { learner, error, retry } = useLearner();
  const [copied, setCopied] = useState(false);
  return (
    <section className="en-card">
      <h1>{t.title}</h1>
      {error != null && <Problem error={error} onRetry={retry} />}
      <p className="en-muted">{t.learner}</p>
      <div className="en-copy">
        <code>{learner ?? vi.english.loading}</code>
        <button
          type="button"
          className="en-button small"
          disabled={!learner}
          onClick={() =>
            learner &&
            navigator.clipboard
              ?.writeText(learner)
              .then(() => setCopied(true))
              .catch(() => undefined)
          }
        >
          {copied ? t.copied : t.copy}
        </button>
      </div>
      <p>{t.draftNote}</p>
      <ul>
        <li>{t.estimates}</li>
        <li>{t.drafts}</li>
        <li>{t.data}</li>
      </ul>
    </section>
  );
}
