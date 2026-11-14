// One learner per browser (specs/web-english, point 9): created once, remembered in localStorage.
export const LEARNER_KEY = "nodetrail_english_learner";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function storedLearner(store: KeyValueStore | null): string | null {
  try {
    const value = store?.getItem(LEARNER_KEY) ?? null;
    return value && UUID.test(value) ? value : null;
  } catch {
    return null; // private mode or blocked storage: a new learner is created
  }
}

export async function ensureLearner(
  store: KeyValueStore | null,
  create: () => Promise<string>,
): Promise<string> {
  const known = storedLearner(store);
  if (known) return known;
  const id = await create();
  try {
    store?.setItem(LEARNER_KEY, id);
  } catch {
    // remembered for this page only
  }
  return id;
}

export function browserStore(): KeyValueStore | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
