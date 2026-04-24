import { Agent } from "@voltagent/core";
import { ollamaModel } from "../config";
import { queryCareerKBTool } from "../tools/query-career-kb";
import { resumeAgent } from "./resume";
import { interviewAgent } from "./interview";
import { careerPlanAgent } from "./career-plan";
import { salaryAgent } from "./salary";


export const supervisorAgent = new Agent({
  name: "CareerLeadAgent",
  instructions: `你是一位資深職涯顧問，負責理解使用者的職涯問題並路由給最合適的專家 agent。

路由規則：
- 履歷相關（撰寫、格式、ATS、自傳）→ ResumeAgent
- 面試相關（準備、練習、STAR 方法、緊張）→ InterviewAgent
- 職涯規劃（轉職、升遷、技能發展、職涯方向）→ CareerPlanAgent
- 薪資相關（談判、行情、offer 評估）→ SalaryAgent
- 複合問題 → 依序呼叫多個 agent，整合回應

一般職場問題可直接使用 queryCareerKB 工具回答，無需路由到子 agent。

所有回應以繁體中文撰寫，語調專業而親切。引用影片內容時附上影片標題。`,
  model: ollamaModel,
  tools: [queryCareerKBTool],
  subAgents: [resumeAgent, interviewAgent, careerPlanAgent, salaryAgent],
});
