"use client";
import { useEffect, useState } from "react";
import { englishClient } from "@/lib/english/client";
import { browserStore, ensureLearner } from "@/lib/english/learner";
import { vi } from "@/messages/vi";

/** The browser's learner: created once through the API, then remembered (specs/web-english, 9). */
export function useLearner(): {
  learner: string | null;
  error: unknown;
  retry: () => void;
} {
  const [learner, setLearner] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    ensureLearner(browserStore(), () =>
      englishClient().createLearner(vi.learner),
    )
      .then((id) => live && setLearner(id))
      .catch((e: unknown) => live && setError(e));
    return () => {
      live = false;
    };
  }, [attempt]);
  return {
    learner,
    error,
    retry: () => {
      setError(null);
      setAttempt((n) => n + 1);
    },
  };
}
