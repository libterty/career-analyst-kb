import { createTool } from "@voltagent/core";
import { z } from "zod";
import { fetchCareerKB } from "./kb-client";

const TOPIC_VALUES = [
  "resume",
  "interview",
  "career_planning",
  "salary",
  "workplace",
  "job_search",
  "promotion",
  "industry_insight",
  "skill_development",
  "general_career",
] as const;

export const queryCareerKBTool = createTool({
  name: "queryCareerKB",
  description:
    "Query the career knowledge base built from @hrjasmin YouTube videos. " +
    "Returns an answer grounded in real video content, with source citations.",
  parameters: z.object({
    question: z.string().describe("The career-related question to answer"),
    topic: z
      .enum(TOPIC_VALUES)
      .optional()
      .describe("Narrow search to a specific topic; omit to search all"),
    sessionId: z.string().default("voltagent-default"),
  }),
  execute: async ({ question, topic, sessionId }) => {
    const data = await fetchCareerKB(question, topic, sessionId);
    return {
      answer: data.answer,
      sources: data.sources.map((s) => ({
        title: s.video_title,
        url: s.url,
        topic: s.section,
        score: s.score,
      })),
    };
  },
});
