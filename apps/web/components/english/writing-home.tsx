"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { englishClient } from "@/lib/english/client";
import type { EssaySummary, WritingPrompt } from "@/lib/english/types";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { useLearner } from "./use-learner";

const t = vi.english;
const w = t.writing;

export function promptTypeLabel(type: string): string {
  return w.types[type] ?? type;
}

/** Prompts to write on, and the learner's essays (specs/writing/step-2.1.md). */
export function WritingHome() {
  const { learner, error: learnerError, retry } = useLearner();
  const [prompts, setPrompts] = useState<WritingPrompt[] | null>(null);
  const [essays, setEssays] = useState<EssaySummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!learner) return;
    let live = true;
    const client = englishClient();
    Promise.all([client.writingPrompts(learner), client.essays(learner)])
      .then(([p, e]) => {
        if (!live) return;
        setPrompts(p);
        setEssays(e);
        setError(null);
      })
      .catch((e: unknown) => live && setError(e));
    return () => {
      live = false;
    };
  }, [learner, version]);

  if (learnerError) return <Problem error={learnerError} onRetry={retry} />;
  if (error)
    return <Problem error={error} onRetry={() => setVersion((n) => n + 1)} />;
  if (!prompts || !essays) return <p className="en-muted">{t.loading}</p>;
  const promptText = new Map(prompts.map((p) => [p.id, p.prompt]));

  return (
    <>
      <section className="en-card">
        <h1>{w.title}</h1>
        <p className="en-muted">{w.intro}</p>
      </section>
      <section className="en-card">
        <h2>{w.prompts}</h2>
        {prompts.length === 0 && <p className="en-muted">{w.noPrompts}</p>}
        <ul className="en-essays">
          {prompts.map((p) => (
            <li key={p.id}>
              <div className="en-actions">
                <span className="en-badge next">
                  {w.task} {p.task} · {p.level}
                </span>
                <span className="en-muted">{promptTypeLabel(p.type)}</span>
                {p.status === "draft" && (
                  <span className="en-badge">{t.draft}</span>
                )}
              </div>
              <p lang="en">{p.prompt}</p>
              <Link className="en-button" href={`/viet/${p.id}`}>
                {w.write}
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <section className="en-card">
        <h2>{w.yours}</h2>
        {essays.length === 0 && <p className="en-muted">{w.none}</p>}
        <ul className="en-essays">
          {essays.map((e) => (
            <li key={e.id} data-essay-id={e.id}>
              <p lang="en" className="en-clamp">
                {promptText.get(e.prompt_id) ?? e.prompt_id}
              </p>
              <p className="en-muted">
                {new Date(e.submitted_at).toLocaleString("vi-VN")} ·{" "}
                {w.status[e.status]}
                {e.words !== null && ` · ${e.words} ${w.words}`}
              </p>
              <Link className="en-link" href={`/bai-viet/${e.id}`}>
                {w.open}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
