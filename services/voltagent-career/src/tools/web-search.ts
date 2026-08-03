import { createTool } from "@voltagent/core";
import { z } from "zod";
import { config } from "../config";

const searchResultSchema = z.object({
  title: z.string(),
  url: z.string(),
  content: z.string(),
});

// SearXNG 是內部服務，重試延遲沒有意義（無 backoff）——見
// docs/graph-design/graph-migration-plan.md「Next Migration Step」的分析：
// 這是單點可靠性缺陷，不需要 Graph 化，只需要有限重試 + 明確 fallback。
const MAX_FETCH_ATTEMPTS = 2;

async function fetchSearxng(url: URL): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= MAX_FETCH_ATTEMPTS; attempt++) {
    try {
      const response = await fetch(url.toString(), {
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) {
        throw new Error(`SearXNG 搜尋失敗：HTTP ${response.status}`);
      }
      return response;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

export const webSearchTool = createTool({
  name: "webSearch",
  description:
    "搜尋網路上的最新資訊。適用於特定公司薪資行情、產業就業市況、主管管理課題、職場相處問題、最新科技趨勢等需要即時資訊的問題。若搜尋暫時無法使用，會回傳 available=false，請改用職涯教練知識庫的一般建議並誠實告知使用者。",
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

    try {
      const response = await fetchSearxng(url);
      const data = (await response.json()) as {
        results?: Array<{ title?: string; url?: string; content?: string }>;
      };

      const results = (data.results ?? []).slice(0, numResults).map((r) =>
        searchResultSchema.parse({
          title: r.title ?? "",
          url: r.url ?? "",
          content: r.content ?? "",
        }),
      );

      return { query, results, available: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(
        `[webSearchTool] SearXNG unavailable after retry: ${message}`,
      );
      return {
        query,
        results: [],
        available: false,
        error:
          "即時搜尋暫時無法使用，請改用職涯教練知識庫的一般建議回答，並誠實告知使用者目前無法提供即時資訊。",
      };
    }
  },
});
