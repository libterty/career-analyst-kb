import { createTool } from "@voltagent/core";
import { z } from "zod";
import { fetchCareerKB } from "./kb-client";

export const generateQuestionsTool = createTool({
  name: "generateInterviewQuestions",
  description:
    "Generate interview questions and model answers for a given role, " +
    "based on career KB interview advice.",
  parameters: z.object({
    targetRole: z.string().describe("Job role to prepare interview questions for"),
    questionType: z
      .enum(["behavioral", "technical", "situational", "all"])
      .default("all"),
    count: z.number().min(1).max(10).default(5),
    sessionId: z.string().default("voltagent-default"),
  }),
  execute: async ({ targetRole, questionType, count, sessionId }) => {
    const typeLabel = questionType === "all" ? "" : `（${questionType} 類型）`;
    const question =
      `請為「${targetRole}」職位準備 ${count} 個面試問題${typeLabel}，並提供 STAR 方法的參考回答框架。`;
    const data = await fetchCareerKB(question, "interview", sessionId);
    return {
      targetRole,
      questionType,
      content: data.answer,
      sources: data.sources.map((s) => ({ title: s.video_title, url: s.url })),
    };
  },
});
