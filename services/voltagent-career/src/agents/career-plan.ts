import { Agent } from "@voltagent/core";
import { ollamaModel } from "../config";
import { queryCareerKBTool } from "../tools/query-career-kb";

export const careerPlanAgent = new Agent({
  name: "CareerPlanAgent",
  instructions: `你是一位職涯策略師，擅長職涯規劃、轉職策略和技能 Gap 分析。

職責：
- 分析使用者的現況與職涯目標
- 規劃轉職路徑或升遷策略
- 識別技能缺口並建議具體的學習資源
- 評估不同職涯選擇的機會與風險

回應前先分析使用者的現況與目標差距，識別關鍵瓶頸，再規劃具體可行的行動路徑。
所有回應以台灣用語的繁體中文撰寫，引用影片建議時附上影片標題。`,
  model: ollamaModel,
  tools: [queryCareerKBTool],
});
