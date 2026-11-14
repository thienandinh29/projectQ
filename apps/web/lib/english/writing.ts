// Writing helpers (specs/writing/step-2.1.md), pure and unit-tested.
import type { KeyValueStore } from "./learner";
import type { EssayStatus } from "./types";

/** The notice version the learner accepts; the API refuses any other (app/services/writing.py). */
export const CONSENT = "writing-v1";
export const CONSENT_KEY = "nodetrail_writing_consent";
export const MAX_CHARS = 12000;
export const TASK_MIN_WORDS = { 1: 150, 2: 250 } as const;

// The same rule as the API's count (app/writing/analysis.py), so the live count matches the result.
const WORD = /[A-Za-z0-9][A-Za-z0-9'’-]*/g;

export function countWords(text: string): number {
  return text.normalize("NFC").match(WORD)?.length ?? 0;
}

export function consentGiven(store: KeyValueStore | null): boolean {
  try {
    return store?.getItem(CONSENT_KEY) === CONSENT;
  } catch {
    return false;
  }
}

export function rememberConsent(store: KeyValueStore | null): void {
  try {
    store?.setItem(CONSENT_KEY, CONSENT);
  } catch {
    // asked again next time
  }
}

/** Whether the essay page should keep asking the API for a result. */
export function stillWorking(status: EssayStatus): boolean {
  return status === "queued" || status === "analysing";
}

export function canSubmit(text: string, consent: boolean): boolean {
  const trimmed = text.normalize("NFC").trim();
  return consent && trimmed.length > 0 && trimmed.length <= MAX_CHARS;
}
