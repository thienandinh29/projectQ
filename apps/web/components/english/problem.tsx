import { DataError } from "@/lib/decode";
import { vi } from "@/messages/vi";

const t = vi.english;

export function problemText(error: unknown): string {
  if (error instanceof DataError) {
    if (error.code === "failed" && error.status === 409) return t.noItems;
    if (error.code === "contract") return t.contract;
  }
  return t.offline;
}

/** A failure says what happened and offers a retry; nothing is invented in its place. */
export function Problem({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  return (
    <div className="en-problem" role="alert">
      <p>{problemText(error)}</p>
      {onRetry && (
        <button type="button" className="en-button secondary" onClick={onRetry}>
          {t.retry}
        </button>
      )}
    </div>
  );
}
