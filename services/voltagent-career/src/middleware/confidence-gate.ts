import { createInputMiddleware, extractText } from "@voltagent/core";
import type { UIMessage } from "ai";
import { classifyRouting } from "./routing-classifier";

const CONFIDENCE_THRESHOLD = 0.7;

function getQueryText(input: string | UIMessage[] | unknown[]): string {
  if (typeof input === "string") return input;

  const messages = input as UIMessage[];
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg && msg.role === "user") {
      return extractText(msg as Parameters<typeof extractText>[0]);
    }
  }
  return "";
}

export const confidenceGate = createInputMiddleware({
  id: "confidence-gate",
  name: "Routing Confidence Gate",
  description:
    "Low-confidence routing redirects supervisor to answer directly instead of delegating",
  async handler(args) {
    const queryText = getQueryText(args.input as string | UIMessage[]);
    if (!queryText.trim()) return undefined;

    let decision;
    try {
      decision = await classifyRouting(queryText);
    } catch {
      // Classifier failure: let supervisor proceed normally
      return undefined;
    }

    if (decision.confidence < CONFIDENCE_THRESHOLD) {
      const fallbackInstruction = `\n\n[系統提示：路由信心分數偏低（${decision.confidence.toFixed(2)}），請直接回答此問題，不要路由給子 agent。在回答結尾加上：<!-- routing_fallback:true -->]`;

      if (typeof args.input === "string") {
        return args.input + fallbackInstruction;
      }

      // For message arrays: append fallback note to last user message text
      const messages = args.input as UIMessage[];
      return messages.map((msg, idx) => {
        if (idx === messages.length - 1 && msg.role === "user") {
          const text = getQueryText([msg]);
          return {
            ...msg,
            content: [{ type: "text" as const, text: text + fallbackInstruction }],
          };
        }
        return msg;
      });
    }

    return undefined;
  },
});
