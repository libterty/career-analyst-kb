import { config } from "../config";

export interface KBResult {
  answer: string;
  sources: Array<{ video_title: string; url: string; section: string; score: number }>;
}

export async function fetchCareerKB(
  question: string,
  topic?: string,
  sessionId = "voltagent-default",
): Promise<KBResult> {
  const body: Record<string, unknown> = { question, session_id: sessionId, language: "zh-TW" };
  if (topic) body.topic = topic;

  const res = await fetch(`${config.kbApiUrl}/api/chat/query/sync`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.kbApiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`KB API error ${res.status}: ${await res.text()}`);
  return res.json() as Promise<KBResult>;
}
