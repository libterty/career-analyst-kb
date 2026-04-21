import { createTool } from "@voltagent/core";
import { z } from "zod";
import { fetchCareerKB } from "./kb-client";

export const analyzeResumeTool = createTool({
  name: "analyzeResume",
  description:
    "Analyze a resume and provide structured feedback on content, format, and ATS optimization, " +
    "grounded in career KB advice.",
  parameters: z.object({
    resumeText: z.string().describe("Full text of the resume to analyze"),
    targetRole: z.string().optional().describe("Target job role or industry"),
    sessionId: z.string().default("voltagent-default"),
  }),
  execute: async ({ resumeText, targetRole, sessionId }) => {
    const roleContext = targetRole ? `，目標職位：${targetRole}` : "";
    const question =
      `請根據以下履歷內容${roleContext}，提供具體的改善建議：\n\n${resumeText.slice(0, 1500)}`;
    const data = await fetchCareerKB(question, "resume", sessionId);
    return {
      feedback: data.answer,
      sources: data.sources.map((s) => ({ title: s.video_title, url: s.url })),
      targetRole: targetRole ?? "未指定",
    };
  },
});
