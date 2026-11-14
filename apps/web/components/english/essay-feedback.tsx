import { CRITERIA, type EssayResult } from "@/lib/english/types";
import { vi } from "@/messages/vi";

const w = vi.english.writing;

/** The model's feedback; every quote shown was checked to be in the essay (step 2.4). */
export function EssayFeedbackView({ result }: { result: EssayResult }) {
  if (result.feedback === undefined) return null; // analysed before step 2.4
  if (result.feedback === null)
    return result.feedbackUnavailableVi ? (
      <section className="en-card">
        <h2>{w.feedback}</h2>
        <p className="en-muted">{result.feedbackUnavailableVi}</p>
      </section>
    ) : null;
  const fb = result.feedback;
  return (
    <section className="en-card" data-testid="essay-feedback">
      <h2>{w.feedback}</h2>
      <p className="en-muted">{w.feedbackNote}</p>
      {CRITERIA.map((c) =>
        fb.criteria[c].length === 0 ? null : (
          <div key={c} className="en-criterion">
            <h3>{w.criteria[c]}</h3>
            <ul>
              {fb.criteria[c].map((p, i) => (
                <li key={i} data-kind={p.kind}>
                  <span className="en-badge">
                    {p.kind === "strength" ? w.strength : w.toImprove}
                  </span>{" "}
                  {p.point_vi}
                  {p.quotes.map((q) => (
                    <q key={q} lang="en">
                      {q}
                    </q>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        ),
      )}
      {fb.dropped > 0 && (
        <p className="en-muted">
          {w.droppedPoints.replace("{n}", String(fb.dropped))}
        </p>
      )}
    </section>
  );
}
