import { createTool } from "@voltagent/core";
import { z } from "zod";
import { fetchCareerKB } from "./kb-client";

export const analyzeJobDescriptionTool = createTool({
  name: "analyzeJobDescription",
  description:
    "Analyze a job description to extract required skills, responsibilities, and red flags. " +
    "Optionally compare against the candidate's background to identify gaps and suggest preparation strategies.",
  parameters: z.object({
    jdText: z.string().describe("Full text of the job description"),
    resumeText: z
      .string()
      .optional()
      .describe("Candidate's resume text for gap analysis (optional)"),
    targetRole: z
      .string()
      .optional()
      .describe("Job title / role name if not clear from JD"),
    sessionId: z.string().default("voltagent-default"),
  }),
  execute: async ({ jdText, resumeText, targetRole, sessionId }) => {
    const role = targetRole ?? "該職位";
    const jdSnippet = jdText.slice(0, 1200);
    const resumeSnippet = resumeText?.slice(0, 800) ?? "";

    const gapSection = resumeText
      ? `\n\n候選人背景（部分）：\n${resumeSnippet}\n\n請同時分析與職缺的契合度與技能缺口。`
      : "";

    const question =
      `請分析以下「${role}」職缺描述，提供：\n` +
      `1. 必要技能與資格（must-have）\n` +
      `2. 加分條件（nice-to-have）\n` +
      `3. 職責重點摘要\n` +
      `4. 履歷關鍵字（ATS 優化用）\n` +
      `5. 面試可能聚焦的題型與準備方向` +
      gapSection +
      `\n\n職缺描述：\n${jdSnippet}`;

    const data = await fetchCareerKB(question, "job_search", sessionId);

    return {
      role,
      analysis: data.answer,
      sources: data.sources.map((s) => ({ title: s.video_title, url: s.url })),
      hasGapAnalysis: !!resumeText,
    };
  },
});
