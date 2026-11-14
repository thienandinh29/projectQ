"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DataError } from "@/lib/decode";
import { englishClient } from "@/lib/english/client";
import {
  LINKING_GROUPS,
  type Essay,
  type EssayResult,
  type GrammarIssue,
} from "@/lib/english/types";
import { stillWorking } from "@/lib/english/writing";
import { vi } from "@/messages/vi";
import { Problem } from "./problem";
import { useLearner } from "./use-learner";

const t = vi.english;
const w = t.writing;
const POLL_MS = 2000;
const POLL_LIMIT = 60; // about two minutes, then the page says the worker may be down

function Result({ result }: { result: EssayResult }) {
  const used = LINKING_GROUPS.filter(
    (g) => Object.keys(result.linking[g] ?? {}).length > 0,
  );
  return (
    <section className="en-card" data-testid="essay-result">
      <h2>{w.result}</h2>
      <p className="en-muted">{w.measured}</p>
      <dl className="en-measures">
        <div>
          <dt>{w.wordCount}</dt>
          <dd>
            {result.words} / {result.min_words}
          </dd>
        </div>
        <div>
          <dt>{w.sentences}</dt>
          <dd>{result.sentences}</dd>
        </div>
        <div>
          <dt>{w.paragraphs}</dt>
          <dd>{result.paragraphs}</dd>
        </div>
        <div>
          <dt>{w.avgSentence}</dt>
          <dd>
            {result.avg_sentence_words.toFixed(1)} {w.words}
          </dd>
        </div>
        <div>
          <dt>{w.longest}</dt>
          <dd>
            {result.longest_sentence_words} {w.words}
          </dd>
        </div>
      </dl>
      <p>
        {result.long_enough
          ? w.enough
          : `${w.short} ${result.min_words} ${w.words}.`}
      </p>
      <h3>
        {w.linking} ({result.linking_groups_used} {w.groupsUsed})
      </h3>
      {used.length === 0 && <p className="en-muted">{w.noLinking}</p>}
      <ul className="en-linking">
        {used.map((g) => (
          <li key={g}>
            <strong>{w.groups[g]}:</strong>{" "}
            <span lang="en">
              {Object.entries(result.linking[g] ?? {})
                .map(([phrase, n]) => (n > 1 ? `${phrase} ×${n}` : phrase))
                .join(", ")}
            </span>
          </li>
        ))}
      </ul>
      {result.complexity && (
        <>
          <h3>{w.complexity}</h3>
          <p>
            {result.complexity.clauses_per_sentence.toFixed(1)}{" "}
            {w.clausesPerSentence} ·{" "}
            {Math.round(result.complexity.complex_sentence_share * 100)}%{" "}
            {w.complexShare}
          </p>
        </>
      )}
    </section>
  );
}

/**
 * Why an error did not move the roadmap. If the essay moved anything, the draft rule was not in
 * effect, so a mapped error was left out by the cap (at most 3 per essay, one per part).
 */
export function notCountedReason(
  issues: GrammarIssue[],
): (issue: GrammarIssue) => string {
  const applied = issues.some((i) => i.evidence);
  return (issue) =>
    !issue.node
      ? w.notRecorded
      : applied
        ? w.notRecordedCap
        : w.notRecordedDraft;
}

/** The sentence with the error's span marked. */
function Marked({ issue }: { issue: GrammarIssue }) {
  const from = issue.start - issue.sentence_start;
  const to = from + issue.end - issue.start;
  return (
    <p lang="en" className="en-issue-sentence">
      {issue.sentence.slice(0, from)}
      <mark>{issue.sentence.slice(from, to)}</mark>
      {issue.sentence.slice(to)}
    </p>
  );
}

export function Grammar({ result }: { result: EssayResult }) {
  if (result.grammar === undefined) return null; // analysed before step 2.2
  if (result.grammar === null)
    return (
      <section className="en-card">
        <h2>{w.grammar}</h2>
        <p className="en-muted">{result.grammarUnavailableVi ?? w.noGrammar}</p>
      </section>
    );
  const { issues } = result.grammar;
  const why = notCountedReason(issues);
  return (
    <section className="en-card" data-testid="essay-grammar">
      <h2>{w.grammar}</h2>
      <p className="en-muted">{w.grammarNote}</p>
      {issues.length === 0 && <p>{w.noIssues}</p>}
      <ul className="en-issues">
        {issues.map((issue) => (
          <li key={issue.id} data-errant-type={issue.errant_type ?? ""}>
            <Marked issue={issue} />
            {issue.suggestion !== null && (
              <p>
                {w.suggestion}: <strong lang="en">{issue.suggestion}</strong>
              </p>
            )}
            {issue.explain_vi && <p>{issue.explain_vi}</p>}
            {issue.evidence && issue.node ? (
              <Link className="en-link" href={`/on-tap/phan/${issue.node}`}>
                {w.recorded}: {issue.node_vi ?? issue.node}
              </Link>
            ) : (
              <p className="en-muted">{why(issue)}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One essay: follows its status until the worker is done, then shows what was measured. */
export function EssayView({ essayId }: { essayId: string }) {
  const router = useRouter();
  const { learner, error: learnerError, retry } = useLearner();
  const [essay, setEssay] = useState<Essay | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [polls, setPolls] = useState(0);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!learner) return;
    if (essay && (!stillWorking(essay.status) || polls >= POLL_LIMIT)) return;
    let live = true;
    const timer = setTimeout(
      () =>
        englishClient()
          .essay(learner, essayId)
          .then((e) => {
            if (!live) return;
            setEssay(e);
            setError(null);
            setPolls((n) => n + 1);
          })
          .catch((e: unknown) => live && setError(e)),
      essay ? POLL_MS : 0,
    );
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [learner, essayId, essay, polls]);

  if (learnerError) return <Problem error={learnerError} onRetry={retry} />;
  if (
    error instanceof DataError &&
    error.code === "failed" &&
    error.status === 404
  )
    return (
      <section className="en-card">
        <p className="en-problem">{w.notFound}</p>
        <Link className="en-link" href="/viet">
          {w.back}
        </Link>
      </section>
    );
  if (error && !essay)
    return <Problem error={error} onRetry={() => setPolls((n) => n + 1)} />;
  if (!learner || !essay) return <p className="en-muted">{t.loading}</p>;

  async function remove() {
    if (!learner || deleting || !window.confirm(w.confirmDelete)) return;
    setDeleting(true);
    try {
      await englishClient().deleteEssay(learner, essayId);
      router.push("/viet");
    } catch (e: unknown) {
      setError(e);
      setDeleting(false);
    }
  }

  const working = stillWorking(essay.status);
  return (
    <>
      <section className="en-card">
        <h1>{w.status[essay.status]}</h1>
        {essay.prompt && (
          <p lang="en" className="en-prompt">
            {essay.prompt.prompt}
          </p>
        )}
        {working && (
          <p className="en-muted" aria-live="polite">
            {polls >= POLL_LIMIT ? w.slow : w.waiting}
          </p>
        )}
        {essay.status === "failed" && (
          <p className="en-problem">{essay.failure_vi}</p>
        )}
      </section>
      {essay.result && <Result result={essay.result} />}
      {essay.result && <Grammar result={essay.result} />}
      <section className="en-card">
        <h2>{w.yourText}</h2>
        <div lang="en" className="en-essay-text">
          {essay.text.split(/\n\s*\n/).map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </div>
        {error !== null && <Problem error={error} />}
        <div className="en-actions">
          <Link className="en-button secondary" href="/viet">
            {w.back}
          </Link>
          <button
            type="button"
            className="en-link"
            disabled={deleting}
            onClick={remove}
          >
            {w.delete}
          </button>
        </div>
      </section>
    </>
  );
}
