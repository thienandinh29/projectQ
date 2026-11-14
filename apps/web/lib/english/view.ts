// Pure helpers the English screens use, kept out of components so they are unit-tested.
import type { Level, Milestone, MilestoneStatus, Roadmap } from "./types";
import { LEVELS } from "./types";

export function optionForKey(key: string, options: string[]): string | null {
  const n = Number(key);
  return Number.isInteger(n) && n >= 1 && n <= options.length
    ? options[n - 1]
    : null;
}

export function statusLabel(
  status: MilestoneStatus,
  labels: Record<MilestoneStatus, string>,
): string {
  return labels[status];
}

/** Milestones grouped by level, in the API's learning order, lowest level first. */
export function byLevel(roadmap: Roadmap): [Level, Milestone[]][] {
  return LEVELS.map(
    (level) =>
      [level, roadmap.milestones.filter((m) => m.level === level)] as [
        Level,
        Milestone[],
      ],
  ).filter(([, ms]) => ms.length > 0);
}

/** Hidden nodes are shown when the milestone needs review or the learner opened it. */
export function showHidden(m: Milestone, opened: boolean): boolean {
  return opened || m.status === "partial";
}

export function progressText(
  number: number,
  total: number | null,
  word: string,
): string {
  return total === null ? `${word} ${number}` : `${word} ${number}/${total}`;
}

export function percent(p: number): number {
  return Math.round(Math.max(0, Math.min(1, p)) * 100);
}

/** Why a vocabulary session is empty: today's work is done, or the list has no new words left. */
export function emptyVocabReason(newLeftToday: number): "done" | "noMoreWords" {
  return newLeftToday === 0 ? "done" : "noMoreWords";
}
