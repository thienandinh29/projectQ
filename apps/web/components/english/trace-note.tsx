import type { DecisionTrace } from "@/lib/contracts";
import { percent } from "@/lib/english/view";
import { vi } from "@/messages/vi";

const t = vi.english;

/** "Vì sao?": the engine's own explanation, with the numbers it used. */
export function TraceNote({
  trace,
  names,
}: {
  trace: DecisionTrace;
  names: Record<string, string>;
}) {
  return (
    <details className="en-trace">
      <summary>{t.roadmap.why}</summary>
      <p>{trace.rule_vi}</p>
      {trace.prior != null && (
        <p className="en-muted">
          {t.trace.before}: {percent(trace.prior)}%
          {trace.posterior != null &&
            ` · ${t.trace.after}: ${percent(trace.posterior)}%`}
        </p>
      )}
      {trace.alternatives && trace.alternatives.length > 0 && (
        <>
          <p className="en-muted">{t.trace.others}:</p>
          <ul>
            {trace.alternatives.map((a) => (
              <li key={a.concept_slug}>
                {names[a.concept_slug] ?? a.concept_slug}: {a.why_not_vi}
              </li>
            ))}
          </ul>
        </>
      )}
    </details>
  );
}
