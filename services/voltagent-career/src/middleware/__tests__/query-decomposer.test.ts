import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../gateway/model-gateway", () => ({
  fastModel: {},
}));

vi.mock("ai", () => ({
  generateText: vi.fn(),
  Output: { object: vi.fn(() => ({})) },
  extractText: vi.fn((msg: { content: unknown }) => {
    if (typeof msg.content === "string") return msg.content;
    if (Array.isArray(msg.content)) {
      return (msg.content as { type: string; text: string }[])
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("");
    }
    return "";
  }),
}));

vi.mock("@voltagent/core", () => ({
  createInputMiddleware: vi.fn((cfg) => cfg),
  extractText: vi.fn((msg: { content: unknown }) => {
    if (typeof msg.content === "string") return msg.content;
    if (Array.isArray(msg.content)) {
      return (msg.content as { type: string; text: string }[])
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("");
    }
    return "";
  }),
}));

import {
  decomposeQuery,
  injectSubQuestions,
  queryDecomposer,
} from "../query-decomposer";
import { generateText } from "ai";

const mockGenerateText = vi.mocked(generateText);

// The mock returns the raw config object due to createInputMiddleware mock
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const middlewareHandler = (queryDecomposer as any).handler as (args: {
  input: unknown;
  context: unknown;
}) => Promise<unknown>;

describe("decomposeQuery", () => {
  beforeEach(() => mockGenerateText.mockReset());

  it("returns isComplex=true with sub-questions for multi-topic query", async () => {
    const mock = {
      isComplex: true,
      subQuestions: ["如何撰寫履歷？", "面試前需準備什麼？", "薪資如何談判？"],
      reason: "包含三個獨立職涯主題",
    };
    mockGenerateText.mockResolvedValueOnce({ output: mock } as Awaited<
      ReturnType<typeof generateText>
    >);

    const result = await decomposeQuery(
      "我想了解如何寫好履歷，面試要準備什麼，以及薪資談判的技巧",
    );

    expect(result.isComplex).toBe(true);
    expect(result.subQuestions).toHaveLength(3);
    expect(result.subQuestions[0]).toBe("如何撰寫履歷？");
  });

  it("returns isComplex=false with empty subQuestions for single-topic query", async () => {
    const mock = {
      isComplex: false,
      subQuestions: [],
      reason: "只詢問履歷撰寫一個主題",
    };
    mockGenerateText.mockResolvedValueOnce({ output: mock } as Awaited<
      ReturnType<typeof generateText>
    >);

    const result = await decomposeQuery("如何撰寫一份有競爭力的履歷？");

    expect(result.isComplex).toBe(false);
    expect(result.subQuestions).toHaveLength(0);
  });
});

describe("injectSubQuestions", () => {
  it("appends SUB_QUESTIONS tag to string input", () => {
    const result = injectSubQuestions("原始問題", ["子問題一", "子問題二"]);

    expect(typeof result).toBe("string");
    expect(result as string).toContain("[SUB_QUESTIONS:");
    expect(result as string).toContain("子問題一");
    expect(result as string).toContain("子問題二");
  });

  it("appends SUB_QUESTIONS tag to last user message in array", () => {
    // Use unknown[] cast to avoid strict UIMessage type requirements in tests
    const messages = [
      { role: "user", id: "1", content: "第一則訊息" },
      { role: "user", id: "2", content: "最後一則訊息" },
    ] as unknown as Parameters<typeof injectSubQuestions>[0][];

    const result = injectSubQuestions(
      messages as unknown as Parameters<typeof injectSubQuestions>[0],
      ["子問題A"],
    );

    expect(Array.isArray(result)).toBe(true);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const resultMsgs = result as any[];
    // First message unchanged
    expect(resultMsgs[0].content).toBe("第一則訊息");
    // Last message gets the tag injected as content array
    const lastContent = Array.isArray(resultMsgs[1].content)
      ? (resultMsgs[1].content as { type: string; text: string }[])[0]?.text
      : String(resultMsgs[1].content);
    expect(lastContent).toContain("[SUB_QUESTIONS:");
    expect(lastContent).toContain("子問題A");
  });

  it("serializes sub-questions as valid JSON array in the tag", () => {
    const subs = ["q1", "q2", "q3"];
    const result = injectSubQuestions("query", subs) as string;
    // Pattern: [SUB_QUESTIONS:["q1","q2","q3"]] — outer [] wraps the JSON array
    const match = result.match(/\[SUB_QUESTIONS:(\[.*?\])\]/);
    expect(match).not.toBeNull();
    const parsed = JSON.parse(match![1]);
    expect(parsed).toEqual(subs);
  });
});

describe("queryDecomposer middleware handler", () => {
  beforeEach(() => mockGenerateText.mockReset());

  it("returns undefined for short query without parallel words (skips LLM)", async () => {
    const result = await middlewareHandler({
      input: "如何寫履歷",
      context: {},
    });

    expect(result).toBeUndefined();
    expect(mockGenerateText).not.toHaveBeenCalled();
  });

  it("returns undefined for empty input", async () => {
    const result = await middlewareHandler({ input: "", context: {} });

    expect(result).toBeUndefined();
    expect(mockGenerateText).not.toHaveBeenCalled();
  });

  it("calls LLM and injects tag for long complex query", async () => {
    const mock = {
      isComplex: true,
      subQuestions: ["履歷要怎麼寫？", "面試要準備什麼？"],
      reason: "複合問題",
    };
    mockGenerateText.mockResolvedValueOnce({ output: mock } as Awaited<
      ReturnType<typeof generateText>
    >);

    const longQuery =
      "我想了解如何寫一份有競爭力的履歷，同時我也需要知道面試前需要做哪些準備，這樣才能提高面試成功的機率並拿到好的 offer";

    const result = await middlewareHandler({ input: longQuery, context: {} });

    expect(mockGenerateText).toHaveBeenCalledOnce();
    expect(typeof result).toBe("string");
    expect(result as string).toContain("[SUB_QUESTIONS:");
  });

  it("triggers on parallel conjunction word even for short query", async () => {
    const mock = {
      isComplex: true,
      subQuestions: ["如何轉職？", "需要進修什麼技能？"],
      reason: "包含並列詞",
    };
    mockGenerateText.mockResolvedValueOnce({ output: mock } as Awaited<
      ReturnType<typeof generateText>
    >);

    const result = await middlewareHandler({
      input: "我想轉職，並且想了解需要進修哪些技能",
      context: {},
    });

    expect(mockGenerateText).toHaveBeenCalledOnce();
    expect(result).not.toBeUndefined();
  });

  it("returns undefined when LLM says isComplex=false", async () => {
    const mock = { isComplex: false, subQuestions: [], reason: "單一主題" };
    mockGenerateText.mockResolvedValueOnce({ output: mock } as Awaited<
      ReturnType<typeof generateText>
    >);

    const result = await middlewareHandler({
      input:
        "我是應屆畢業生，想知道如何在沒有工作經驗的情況下撰寫一份有競爭力的履歷，讓面試官對我產生興趣並邀請我去面試",
      context: {},
    });

    expect(result).toBeUndefined();
  });

  it("fails open (returns undefined) when LLM throws", async () => {
    mockGenerateText.mockRejectedValueOnce(new Error("LLM timeout"));

    const result = await middlewareHandler({
      input:
        "我想了解履歷寫法以及面試技巧，同時想知道薪資談判的策略，還有如何規劃轉職路徑",
      context: {},
    });

    expect(result).toBeUndefined();
  });

  it("injects multiple sub-questions into output", async () => {
    // UIMessage array injection shape is covered by injectSubQuestions unit tests.
    // Here we verify the middleware correctly passes all sub-questions from LLM output.
    const mock = {
      isComplex: true,
      subQuestions: ["薪資如何談判？", "面試技巧有哪些？"],
      reason: "複合問題",
    };
    mockGenerateText.mockResolvedValueOnce({ output: mock } as Awaited<
      ReturnType<typeof generateText>
    >);

    const query =
      "我想知道薪資談判技巧以及面試準備方式，能不能請你幫我詳細說明這兩個主題的具體做法？";

    const result = (await middlewareHandler({
      input: query,
      context: {},
    })) as string;

    expect(typeof result).toBe("string");
    expect(result).toContain("[SUB_QUESTIONS:");
    expect(result).toContain("薪資如何談判？");
    expect(result).toContain("面試技巧有哪些？");
  });
});
