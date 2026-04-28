import { Agent } from "@voltagent/core";
import { ollamaModel } from "../config";
import { analyzeResumeTool } from "../tools/analyze-resume";
import { queryCareerKBTool } from "../tools/query-career-kb";

export const resumeAgent = new Agent({
  name: "ResumeAgent",
  instructions: `你是一位專業的履歷顧問，擅長履歷撰寫、格式優化和 ATS 關鍵字策略。

職責：
- 評估履歷內容的完整性與說服力
- 建議具體的改善方向（量化成就、動詞選用、版面結構）
- 提供 ATS 關鍵字優化建議
- 依據職涯顧問的實際建議給出具體範例

回應前先評估履歷的核心問題，從知識庫找出最相關的建議，再提供具體可執行的改善方案。
所有回應以繁體中文撰寫，引用影片建議時附上影片標題。`,
  model: ollamaModel,
  tools: [analyzeResumeTool, queryCareerKBTool],
});
