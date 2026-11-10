import { AlertCircle, LoaderCircle } from "lucide-react";
import { vi as t } from "@/messages/vi";
import { DataError } from "@/lib/decode";
import { Button } from "./ui/button";

export function errorMessage(error: unknown) {
  if (error instanceof DataError) {
    if (error.status === 401 || error.status === 403) return t.flow.denied;
    if (error.status === 429) return t.flow.rateLimit;
    if (error.code === "contract") return t.flow.contractError;
    if (error.code === "configuration" || error.code === "unsupported")
      return t.flow.configError;
    if (error.code === "network") return t.flow.networkError;
  }
  return t.flow.requestFailed;
}
export function Loading({ label = t.flow.loading }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <LoaderCircle size={18} className="loading-spinner" />
      {label}
    </div>
  );
}
export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={18} />
      <div>
        <p>{errorMessage(error)}</p>
        {onRetry && (
          <Button variant="ghost" onClick={onRetry}>
            {t.flow.retry}
          </Button>
        )}
      </div>
    </div>
  );
}
