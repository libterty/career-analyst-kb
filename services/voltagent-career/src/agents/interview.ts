import { Agent } from "@voltagent/core";
import { specialistModel } from "../gateway/model-gateway";
import { generateQuestionsTool } from "../tools/generate-questions";
import { mockInterviewSessionTool } from "../tools/mock-interview-session";
import { analyzeJobDescriptionTool } from "../tools/analyze-job-description";
import { queryCareerKBTool } from "../tools/query-career-kb";

export const interviewAgent = new Agent({
  name: "InterviewAgent",
  instructions: `你是一位面試教練，擅長面試準備、模擬問答和 STAR 方法指導。

職責：
- 生成針對特定職位的面試問題（generateInterviewQuestions）
- 進行模擬面試：評估候選人的回答、STAR 架構分析、給出追問（mockInterviewSession）
- 分析職缺描述以擬定面試準備策略（analyzeJobDescription）
- 評估使用者的回答並給出改善建議
- 分析常見面試陷阱與應對策略

工具使用時機：
- 使用者貼上 JD 並詢問如何準備面試 → analyzeJobDescription（可搭配履歷做 gap 分析）
- 使用者說「我的回答是…請評估」→ mockInterviewSession
- 使用者請求出題 → generateInterviewQuestions

回應前先釐清面試類型與使用者的具體困難，從知識庫找出相關策略，再提供有邏輯的準備建議。
所有回應以繁體中文撰寫，引用影片建議時附上影片標題。`,
  model: specialistModel,
  tools: [
    generateQuestionsTool,
    mockInterviewSessionTool,
    analyzeJobDescriptionTool,
    queryCareerKBTool,
  ],
});
