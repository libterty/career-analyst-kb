import { createOutputMiddleware } from "@voltagent/core";
import { generateText, Output } from "ai";
import { z } from "zod";
import { config } from "../config";
import { judgeModel } from "../gateway/model-gateway";

const MAX_RETRIES = 1;

const judgeSchema = z.object({
  score: z.number().int().min(1).max(4),
  reason: z.string(),
});

async function scoreAnswer(
  question: string,
  answer: string,
): Promise<{ score: number; reason: string }> {
  const result = await generateText({
    model: judgeModel,
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore — AI SDK v6 Output.object causes TS2589 deep type recursion; runtime is correct
    output: Output.object({ schema: judgeSchema }),
    prompt: `你是一位職涯顧問品質評審。請根據以下標準為回答評分（1-4分）：

4分：回答完整、具體、有根據，直接解決用戶問題，提供可執行的建議
3分：回答基本正確，有一定實用性，但可更具體或更完整
2分：回答部分相關，但不夠具體或有明顯缺漏
1分：回答不相關、錯誤、或完全沒有幫助

問題：${question}

回答：${answer}

請評分並說明原因。`,
  });

  return result.output as { score: number; reason: string };
}

async function recordKnowledgeGap(
  question: string,
  answer: string,
  score: number,
  reason: string,
): Promise<void> {
  try {
    await fetch(`${config.kbApiUrl}/api/knowledge-gaps`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.kbApiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question, answer, score, reason }),
    });
  } catch {
    // Fire-and-forget: log failure but don't block response
    console.error("[answer-quality] Failed to record knowledge gap");
  }
}

export const answerQualityGate = createOutputMiddleware<string>({
  id: "answer-quality-gate",
  name: "Answer Quality Judge",
  description:
    "Scores every response 1-4; retries once if score < 3; records score ≤ 2 as knowledge gap",
  async handler(args) {
    const answer = args.output;
    if (!answer || typeof answer !== "string") return undefined;
    if (answer.startsWith("[GUARDRAIL_BLOCK]")) return undefined;
    if (answer.includes("超出了職涯顧問系統的服務範圍")) return undefined;

    // Extract user question from context (operation context may carry it)
    const question =
      ((args.context as Record<string, unknown>)?.userMessage as string) ?? "";

    let judgment: { score: number; reason: string };
    try {
      judgment = await scoreAnswer(question, answer);
    } catch {
      // Judge failure: pass through unchanged
      return undefined;
    }

    if (judgment.score <= 2 && question) {
      void recordKnowledgeGap(
        question,
        answer,
        judgment.score,
        judgment.reason,
      );
    }

    if (judgment.score < 3 && args.retryCount < MAX_RETRIES) {
      args.abort(
        `Answer quality score ${judgment.score}/4 (${judgment.reason}). Retrying.`,
        { retry: true },
      );
    }

    return undefined;
  },
});
