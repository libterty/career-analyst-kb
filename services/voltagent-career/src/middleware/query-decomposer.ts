import { createInputMiddleware, extractText } from "@voltagent/core";
import { generateText, Output } from "ai";
import { z } from "zod";
import type { UIMessage } from "ai";
import { fastModel } from "../gateway/model-gateway";

const PARALLEL_WORDS_RE =
  /並且|以及|還有|同時|另外|此外|而且|加上|順便問|還想問|也想了解|也請問|再問/;

const decompositionSchema = z.object({
  isComplex: z.boolean(),
  subQuestions: z.array(z.string()).max(3),
  reason: z.string(),
});

export type DecompositionResult = z.infer<typeof decompositionSchema>;

function getQueryText(input: string | UIMessage[] | unknown[]): string {
  if (typeof input === "string") return input;
  const messages = input as UIMessage[];
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg?.role === "user") {
      return extractText(msg as Parameters<typeof extractText>[0]);
    }
  }
  return "";
}

function isLikelyComplex(text: string): boolean {
  return text.length > 80 || PARALLEL_WORDS_RE.test(text);
}

export async function decomposeQuery(
  userQuery: string,
): Promise<DecompositionResult> {
  const result = await generateText({
    model: fastModel,
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore — AI SDK v6 Output.object causes TS2589 deep type recursion; runtime is correct
    output: Output.object({ schema: decompositionSchema }),
    prompt: `你是一個問題分析器，判斷職涯問題是否為複合問題，並在必要時拆解成子問題。

判斷標準：
- isComplex=true：問題包含 2 個以上獨立職涯主題，或問題超過 80 字且涵蓋多面向
- isComplex=false：問題只有一個主題，或雖然較長但本質是單一問題

若 isComplex=true，將原問題拆解為最多 3 個具體的子問題（每個子問題獨立可查詢）。
若 isComplex=false，subQuestions 設為空陣列。

用戶問題：${userQuery}`,
  });

  return result.output as DecompositionResult;
}

export function injectSubQuestions(
  input: string | UIMessage[],
  subQuestions: string[],
): string | UIMessage[] {
  const tag = `\n\n[SUB_QUESTIONS:${JSON.stringify(subQuestions)}]\n請在呼叫 queryCareerKB 時，將 subQuestions 陣列傳入以獲得更完整的回答。`;

  if (typeof input === "string") {
    return input + tag;
  }

  const messages = input as UIMessage[];
  return messages.map((msg, idx) => {
    if (idx === messages.length - 1 && msg.role === "user") {
      const text = getQueryText([msg]);
      return {
        ...msg,
        content: [{ type: "text" as const, text: text + tag }],
      };
    }
    return msg;
  });
}

export const queryDecomposer = createInputMiddleware({
  id: "query-decomposer",
  name: "Query Decomposer",
  description:
    "Detects complex multi-topic queries and decomposes them into sub-questions for agentic RAG",
  async handler(args) {
    const queryText = getQueryText(args.input as string | UIMessage[]);
    if (!queryText.trim() || !isLikelyComplex(queryText)) return undefined;

    let decision: DecompositionResult;
    try {
      decision = await decomposeQuery(queryText);
    } catch {
      return undefined;
    }

    if (!decision.isComplex || decision.subQuestions.length === 0) {
      return undefined;
    }

    return injectSubQuestions(
      args.input as string | UIMessage[],
      decision.subQuestions,
    );
  },
});
