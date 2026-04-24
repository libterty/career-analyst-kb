import { Agent } from "@voltagent/core";
import { ollamaModel } from "../config";
import { queryCareerKBTool } from "../tools/query-career-kb";


export const salaryAgent = new Agent({
  name: "SalaryAgent",
  instructions: `你是一位薪資談判專家，擅長薪資行情分析和談判策略。

職責：
- 分析不同職位和產業的薪資行情
- 制定薪資談判策略與話術
- 評估 offer 的整體價值（薪資、福利、成長空間）
- 協助使用者建立自信的談判心態

所有回應以繁體中文撰寫，引用影片建議時附上影片標題。`,
  model: ollamaModel,
  tools: [queryCareerKBTool],
});
