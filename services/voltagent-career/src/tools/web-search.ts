import { createTool } from "@voltagent/core";
import { z } from "zod";
import { config } from "../config";

const searchResultSchema = z.object({
  title: z.string(),
  url: z.string(),
  content: z.string(),
});

export const webSearchTool = createTool({
  name: "webSearch",
  description:
    "搜尋網路上的最新資訊。適用於特定公司薪資行情、產業就業市況、主管管理課題、職場相處問題、最新科技趨勢等需要即時資訊的問題。",
  parameters: z.object({
    query: z.string().describe("搜尋關鍵字，建議中英文各一次以獲得更全面結果"),
    numResults: z
      .number()
      .optional()
      .default(5)
      .describe("返回結果數量，預設 5 筆"),
  }),
  execute: async ({ query, numResults = 5 }) => {
    const url = new URL(`${config.searxngUrl}/search`);
    url.searchParams.set("q", query);
    url.searchParams.set("format", "json");
    url.searchParams.set("language", "zh-TW");

    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(15_000),
    });

    if (!response.ok) {
      throw new Error(`SearXNG 搜尋失敗：HTTP ${response.status}`);
    }

    const data = (await response.json()) as {
      results?: Array<{ title?: string; url?: string; content?: string }>;
    };

    const results = (data.results ?? [])
      .slice(0, numResults)
      .map((r) =>
        searchResultSchema.parse({
          title: r.title ?? "",
          url: r.url ?? "",
          content: r.content ?? "",
        }),
      );

    return { query, results };
  },
});
