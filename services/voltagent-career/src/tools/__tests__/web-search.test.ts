import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../../config", () => ({
  config: { searxngUrl: "http://searxng.internal:8080" },
}));

vi.mock("@voltagent/core", () => ({
  createTool: vi.fn((cfg) => cfg),
}));

import { webSearchTool } from "../web-search";

// The mock returns the raw config object due to createTool mock
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const execute = (webSearchTool as any).execute as (args: {
  query: string;
  numResults?: number;
}) => Promise<{
  query: string;
  results: Array<{ title: string; url: string; content: string }>;
  available: boolean;
  error?: string;
}>;

describe("webSearchTool", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("returns available=true with results on a successful search", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        results: [
          { title: "t1", url: "https://a", content: "c1" },
          { title: "t2", url: "https://b", content: "c2" },
        ],
      }),
    });

    const result = await execute({ query: "薪資行情" });

    expect(result.available).toBe(true);
    expect(result.results).toHaveLength(2);
    expect(result.error).toBeUndefined();
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("retries once on transient failure then succeeds", async () => {
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ results: [{ title: "t", url: "https://a", content: "c" }] }),
      });

    const result = await execute({ query: "薪資行情" });

    expect(result.available).toBe(true);
    expect(result.results).toHaveLength(1);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it("returns a structured fallback (not a throw) when SearXNG is unavailable after retry", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 503,
    });

    const result = await execute({ query: "薪資行情" });

    expect(result.available).toBe(false);
    expect(result.results).toEqual([]);
    expect(result.error).toBeTruthy();
    // 1 initial attempt + 1 retry = 2 calls, no more (bounded retry, no infinite loop)
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it("returns a structured fallback when fetch throws on every attempt", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("connection refused"),
    );

    const result = await execute({ query: "薪資行情" });

    expect(result.available).toBe(false);
    expect(result.error).toContain("知識庫");
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it("truncates results to numResults", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        results: [
          { title: "t1", url: "https://a", content: "c1" },
          { title: "t2", url: "https://b", content: "c2" },
          { title: "t3", url: "https://c", content: "c3" },
        ],
      }),
    });

    const result = await execute({ query: "薪資行情", numResults: 2 });

    expect(result.results).toHaveLength(2);
  });
});
