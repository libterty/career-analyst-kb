import { generateText, Output } from "ai";
import { z } from "zod";
import { fastModel } from "../gateway/model-gateway";

export type AgentTarget =
  | "resume"
  | "interview"
  | "career-plan"
  | "salary"
  | "web-search"
  | "direct";

export type RoutingDecision = {
  agent: AgentTarget;
  confidence: number;
  reason: string;
};

const routingSchema = z.object({
  agent: z.enum([
    "resume",
    "interview",
    "career-plan",
    "salary",
    "web-search",
    "direct",
  ]),
  confidence: z.number().min(0).max(1),
  reason: z.string(),
});

export async function classifyRouting(
  userQuery: string,
): Promise<RoutingDecision> {
  const result = await generateText({
    model: fastModel,
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore — AI SDK v6 Output.object causes TS2589 deep type recursion; runtime is correct
    output: Output.object({ schema: routingSchema }),
    prompt: `你是一位職涯問題分類器。根據用戶的問題，判斷應該路由給哪個 agent，並給出信心分數（0-1）。

可用 agents：
- resume: 履歷撰寫、格式優化、ATS、自傳、cover letter
- interview: 面試準備、練習、STAR 方法、面試技巧
- career-plan: 轉職、升遷、技能發展、職涯方向、職涯規劃
- salary: 薪資談判、市場行情、offer 評估、薪水比較
- web-search: 需要即時資訊（含「現在」「最新」「今年」「目前」等時效性詞彙，或詢問特定公司薪資/現況）；主管管理課題（管理團隊、績效面談、新手主管）；職場相處問題（難相處同事、職場霸凌、辦公室政治）
- direct: 一般職場問題、複合問題、意圖不明確

請回傳最適合的 agent 和你的信心分數（0=完全不確定，1=非常確定）。

用戶問題：${userQuery}`,
  });

  return result.output as RoutingDecision;
}
