// The English pack's calls, through the same-origin proxy (/api/backend): the API key stays on the server.
import { DataError } from "@/lib/decode";
import {
  parseLevelResult,
  parseRoadmap,
  parseStep,
  parseVocabAnswer,
  parseVocabSession,
} from "./decode";
import type {
  Level,
  LevelResult,
  Roadmap,
  Step,
  VocabAnswer,
  VocabSession,
} from "./types";

export const VOCAB_LIST = "core-seed";

export const COURSE = "english-ielts";

type Fetch = typeof fetch;

export function englishClient(fetcher: Fetch = (...a) => fetch(...a)) {
  async function request(
    path: string,
    init: RequestInit = {},
  ): Promise<unknown> {
    let response: Response;
    try {
      response = await fetcher(`/api/backend/${path}`, {
        ...init,
        cache: "no-store",
        signal: init.signal ?? AbortSignal.timeout(25000),
      });
    } catch {
      throw new DataError("network");
    }
    if (!response.ok)
      throw new DataError(
        response.status === 503 ? "configuration" : "failed",
        response.status,
      );
    try {
      return await response.json();
    } catch {
      throw new DataError("contract");
    }
  }
  const post = (path: string, body: unknown) =>
    request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  return {
    async createLearner(displayName: string): Promise<string> {
      const d = (await post("learners", { display_name: displayName })) as {
        learner_id?: unknown;
      };
      if (typeof d?.learner_id !== "string") throw new DataError("contract");
      return d.learner_id;
    },
    async startLevelTest(
      learnerId: string,
      target: Level | null,
    ): Promise<Step> {
      return parseStep(
        await post("level-tests", {
          learner_id: learnerId,
          course: COURSE,
          target,
        }),
      );
    },
    async answerLevelTest(
      learnerId: string,
      testId: string,
      itemId: string,
      answer: string,
    ): Promise<Step> {
      return parseStep(
        await post(`level-tests/${testId}/answers`, {
          learner_id: learnerId,
          item_id: itemId,
          answer,
        }),
      );
    },
    async startMilestoneTest(
      learnerId: string,
      milestone: string,
    ): Promise<Step> {
      return parseStep(
        await post(`milestones/${milestone}/tests`, {
          learner_id: learnerId,
          course: COURSE,
        }),
      );
    },
    async startPractice(learnerId: string, node: string): Promise<Step> {
      return parseStep(
        await post(`nodes/${node}/practice`, {
          learner_id: learnerId,
          course: COURSE,
        }),
      );
    },
    async answerRun(
      learnerId: string,
      runId: string,
      itemId: string,
      answer: string,
    ): Promise<Step> {
      return parseStep(
        await post(`grammar-runs/${runId}/answers`, {
          learner_id: learnerId,
          item_id: itemId,
          answer,
        }),
      );
    },
    async vocabSession(learnerId: string): Promise<VocabSession> {
      const q = new URLSearchParams({
        learner_id: learnerId,
        list: VOCAB_LIST,
      });
      return parseVocabSession(await request(`vocab/session?${q}`));
    },
    async vocabAnswer(
      learnerId: string,
      itemId: string,
      answer: string,
    ): Promise<VocabAnswer> {
      return parseVocabAnswer(
        await post("vocab/answers", {
          learner_id: learnerId,
          item_id: itemId,
          answer,
        }),
      );
    },
    async roadmap(learnerId: string): Promise<Roadmap> {
      const q = new URLSearchParams({ learner_id: learnerId, course: COURSE });
      return parseRoadmap(await request(`roadmap?${q}`));
    },
  };
}

export function levelResultOf(step: Step): LevelResult | null {
  return step.finished ? parseLevelResult(step.finished) : null;
}

export type EnglishClient = ReturnType<typeof englishClient>;
