import { ArrowRight } from "lucide-react";
import type { DecisionTrace, KnowledgeGraph } from "@/lib/contracts";
import { vi as t } from "@/messages/vi";

export function TracePanel({
  trace,
  graph,
}: {
  trace?: DecisionTrace;
  graph: KnowledgeGraph;
}) {
  if (!trace) return <p className="empty-inline">{t.flow.traceEmpty}</p>;
  const evidence = trace.evidence;
  const evidenceRows: [string, string | number | boolean | null | undefined][] =
    [
      [t.flow.traceItem, evidence.item_id],
      [
        t.flow.traceCorrect,
        evidence.correct == null
          ? undefined
          : evidence.correct
            ? t.flow.traceYes
            : t.flow.traceNo,
      ],
      [t.flow.traceMisconception, evidence.misconception],
      [t.flow.traceSlip, evidence.slip],
      [t.flow.traceGuess, evidence.guess],
    ];
  const name = (slug: string) =>
    graph.nodes.find((node) => node.slug === slug)?.name_vi || slug;
  return (
    <>
      <p className="trace-concept">
        {t.flow.traceFor}: <strong>{name(trace.concept_slug)}</strong>
      </p>
      {(trace.prior !== null || trace.posterior !== null) && (
        <div className="trace-scores">
          <div>
            <span>{t.before}</span>
            <strong>
              {trace.prior === null ? "—" : `${Math.round(trace.prior * 100)}%`}
            </strong>
          </div>
          <ArrowRight size={22} />
          <div>
            <span>{t.after}</span>
            <strong>
              {trace.posterior === null
                ? "—"
                : `${Math.round(trace.posterior * 100)}%`}
            </strong>
          </div>
        </div>
      )}
      <div className="trace-section">
        <h3>{t.evidence}</h3>
        {evidenceRows.some(([, value]) => value != null) ? (
          <dl>
            {evidenceRows
              .filter(([, value]) => value != null)
              .map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
          </dl>
        ) : (
          <p>{t.flow.traceNoEvidence}</p>
        )}
      </div>
      <div className="trace-section">
        <h3>{t.rule}</h3>
        <p>{trace.rule_vi || t.flow.traceRuleFallback}</p>
        <dl>
          <div>
            <dt>{t.flow.ruleCode}</dt>
            <dd>{trace.rule}</dd>
          </div>
        </dl>
      </div>
      <div className="trace-section">
        <h3>{t.alternatives}</h3>
        {trace.alternatives.length ? (
          trace.alternatives.map((alternative) => (
            <p key={alternative.concept_slug}>
              <strong>
                {name(alternative.concept_slug)} ·{" "}
                {Math.round(alternative.p_known * 100)}%
              </strong>
              <br />
              {alternative.why_not_vi}
            </p>
          ))
        ) : (
          <p>{t.flow.traceAlternativesEmpty}</p>
        )}
      </div>
      <dl className="trace-metadata">
        <div>
          <dt>{t.flow.traceKind}</dt>
          <dd>{trace.kind}</dd>
        </div>
        <div>
          <dt>{t.flow.traceAt}</dt>
          <dd>{trace.at}</dd>
        </div>
      </dl>
    </>
  );
}
