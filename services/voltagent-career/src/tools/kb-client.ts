import { trace } from "@voltagent/core";
import { config } from "../config";

export interface KBResult {
  answer: string;
  sources: Array<{
    video_title: string;
    url: string;
    section: string;
    score: number;
  }>;
  retrieval_iterations?: number;
  relevance_sufficient?: boolean;
}

export async function fetchCareerKB(
  question: string,
  topic?: string,
  sessionId = "voltagent-default",
  subQuestions?: string[],
): Promise<KBResult> {
  const body: Record<string, unknown> = {
    question,
    session_id: sessionId,
    language: "zh-TW",
    agentic: true,
  };
  if (topic) body.topic = topic;
  if (subQuestions && subQuestions.length > 0)
    body.sub_questions = subQuestions.slice(0, 3);

  const headers: Record<string, string> = {
    Authorization: `Bearer ${config.kbApiToken}`,
    "Content-Type": "application/json",
  };
  const activeSpan = trace.getActiveSpan();
  if (activeSpan) {
    headers["x-langfuse-trace-id"] = activeSpan.spanContext().traceId;
  }

  const res = await fetch(`${config.kbApiUrl}/api/chat/query/sync`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok)
    throw new Error(`KB API error ${res.status}: ${await res.text()}`);
  return res.json() as Promise<KBResult>;
}
