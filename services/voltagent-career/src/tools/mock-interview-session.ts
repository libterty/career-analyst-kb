import { createTool } from "@voltagent/core";
import { z } from "zod";
import { fetchCareerKB } from "./kb-client";

export const mockInterviewSessionTool = createTool({
  name: "mockInterviewSession",
  description:
    "Evaluate a candidate's answer to an interview question using the STAR framework, " +
    "then generate the next interview question to continue the mock session.",
  parameters: z.object({
    targetRole: z.string().describe("Job role being interviewed for"),
    interviewQuestion: z
      .string()
      .describe("The interview question that was asked"),
    candidateAnswer: z
      .string()
      .describe("The candidate's answer to evaluate"),
    questionType: z
      .enum(["behavioral", "technical", "situational"])
      .default("behavioral")
      .describe("Type of the current question"),
    sessionId: z.string().default("voltagent-default"),
  }),
  execute: async ({
    targetRole,
    interviewQuestion,
    candidateAnswer,
    questionType,
    sessionId,
  }) => {
    const answerSnippet = candidateAnswer.slice(0, 1000);

    const question =
      `請擔任「${targetRole}」職位的面試官兼教練，針對以下作答進行評估與指導：\n\n` +
      `面試問題（${questionType} 類型）：\n${interviewQuestion}\n\n` +
      `候選人回答：\n${answerSnippet}\n\n` +
      `請提供：\n` +
      `1. STAR 架構評估（情境/任務/行動/結果各項完整度）\n` +
      `2. 回答優點（1-2 點）\n` +
      `3. 具體改善建議（1-2 點）\n` +
      `4. 根據此回答，下一個可能的追問（follow-up question）\n` +
      `5. 如果候選人想強化這個回答，應該補充哪些細節`;

    const data = await fetchCareerKB(question, "interview", sessionId);

    return {
      targetRole,
      questionEvaluated: interviewQuestion,
      questionType,
      evaluation: data.answer,
      sources: data.sources.map((s) => ({ title: s.video_title, url: s.url })),
    };
  },
});
