import { Agent } from "@voltagent/core";
import { ollamaModel } from "../config";
import { generateQuestionsTool } from "../tools/generate-questions";
import { queryCareerKBTool } from "../tools/query-career-kb";

export const interviewAgent = new Agent({
  name: "InterviewAgent",
  instructions: `你是一位面試教練，擅長面試準備、模擬問答和 STAR 方法指導。

職責：
- 生成針對特定職位的面試問題
- 以 STAR 方法（情境、任務、行動、結果）指導回答框架
- 評估使用者的回答並給出改善建議
- 分析常見面試陷阱與應對策略

回應前先釐清面試類型與使用者的具體困難，從知識庫找出相關策略，再提供有邏輯的準備建議。
所有回應以繁體中文撰寫，引用影片建議時附上影片標題。`,
  model: ollamaModel,
  tools: [generateQuestionsTool, queryCareerKBTool],
});
