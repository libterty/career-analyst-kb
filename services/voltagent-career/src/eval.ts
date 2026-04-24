/**
 * VoltAgent Eval — 多代理人回應品質評測
 *
 * 用法：
 *   npx tsx src/eval.ts [--questions 5] [--output /tmp/va_eval.json]
 *
 * 從 eval/golden_dataset.jsonl 取題，透過 supervisorAgent.generateText() 呼叫
 * 完整多代理人管道，並以 Ollama LLM judge 評分 0-4。
 */
import fs from "node:fs";
import path from "node:path";
import { supervisorAgent } from "./agents/supervisor";

const DATASET_PATH = path.resolve(
  __dirname,
  "../../../eval/golden_dataset.jsonl",
);
const RESULTS_DIR = path.resolve(__dirname, "../../../eval/results");
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? "http://localhost:11434";
const JUDGE_MODEL = process.env.JUDGE_MODEL ?? "gemma3:12b";

interface DatasetEntry {
  id: string;
  topic: string;
  question: string;
  expected_keywords: string[];
}

interface EvalResult extends DatasetEntry {
  answer: string;
  latency_ms: number;
  relevance_score: number;
  keyword_hit_rate: number;
  error: string | null;
}

function loadDataset(maxQuestions?: number): DatasetEntry[] {
  const lines = fs
    .readFileSync(DATASET_PATH, "utf8")
    .split("\n")
    .filter(Boolean);
  const entries: DatasetEntry[] = lines.map((l) => JSON.parse(l));
  return maxQuestions ? entries.slice(0, maxQuestions) : entries;
}

async function judgeRelevance(
  question: string,
  answer: string,
): Promise<number> {
  const prompt = `你是一位公正的評審，請評估以下「答案」對於「問題」的相關性與品質。

問題：${question}

答案：${answer.slice(0, 1500)}

請從以下角度評分（0-4 分）：
0 = 完全不相關或無法回答
1 = 略有相關但缺乏具體內容
2 = 中等，有部分回應但不夠完整
3 = 良好，有效回應問題且包含實用建議
4 = 優秀，回應完整、具體、有實例或步驟說明

只輸出一個 0 到 4 的整數，不要有任何其他文字。`;

  try {
    const resp = await fetch(`${OLLAMA_BASE_URL}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: JUDGE_MODEL, prompt, stream: false }),
      signal: AbortSignal.timeout(120_000),
    });
    const data = (await resp.json()) as { response: string };
    const text = (data.response ?? "").trim();
    const score = text[0] && /[0-4]/.test(text[0]) ? parseInt(text[0]) : 0;
    return Math.min(Math.max(score, 0), 4);
  } catch {
    return -1;
  }
}

function keywordHitRate(answer: string, keywords: string[]): number {
  if (keywords.length === 0) return 1;
  const lower = answer.toLowerCase();
  const hits = keywords.filter((kw) => lower.includes(kw.toLowerCase())).length;
  return hits / keywords.length;
}

async function runEval(maxQuestions?: number): Promise<EvalResult[]> {
  const dataset = loadDataset(maxQuestions);
  const results: EvalResult[] = [];

  for (let i = 0; i < dataset.length; i++) {
    const entry = dataset[i];
    process.stdout.write(
      `[${String(i + 1).padStart(2, "0")}/${dataset.length}] ${entry.id} ... `,
    );

    const t0 = performance.now();
    try {
      const result = await Promise.race([
        supervisorAgent.generateText(entry.question, {
          userId: "eval-voltagent",
          conversationId: `va-eval-${entry.id}`,
        }),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("timed out")), 180_000),
        ),
      ]);

      const latencyMs = Math.round(performance.now() - t0);
      const answer = (result as { text?: string }).text ?? "";
      const relevance = await judgeRelevance(entry.question, answer);
      const kwRate = keywordHitRate(answer, entry.expected_keywords);

      console.log(
        `score=${relevance} kw=${Math.round(kwRate * 100)}% ${latencyMs}ms`,
      );
      results.push({
        ...entry,
        answer: answer.slice(0, 300),
        latency_ms: latencyMs,
        relevance_score: relevance,
        keyword_hit_rate: kwRate,
        error: null,
      });
    } catch (e) {
      const latencyMs = Math.round(performance.now() - t0);
      const msg = e instanceof Error ? e.message : String(e);
      console.log(`ERROR: ${msg}`);
      results.push({
        ...entry,
        answer: "",
        latency_ms: latencyMs,
        relevance_score: -1,
        keyword_hit_rate: 0,
        error: msg,
      });
    }
  }

  return results;
}

function printSummary(results: EvalResult[]): void {
  const valid = results.filter((r) => r.error === null);
  const judged = valid.filter((r) => r.relevance_score >= 0);

  console.log("\n" + "=".repeat(60));
  console.log("VOLTAGENT EVAL SUMMARY");
  console.log("=".repeat(60));
  console.log(`Total entries:     ${results.length}`);
  console.log(`Successful calls:  ${valid.length}`);
  console.log(`Errors:            ${results.length - valid.length}`);

  if (judged.length > 0) {
    const avgScore =
      judged.reduce((s, r) => s + r.relevance_score, 0) / judged.length;
    console.log(`Avg relevance:     ${avgScore.toFixed(2)} / 4.0`);
    const dist = Object.fromEntries(
      [0, 1, 2, 3, 4].map((i) => [
        i,
        judged.filter((r) => r.relevance_score === i).length,
      ]),
    );
    console.log(`Score dist:        ${JSON.stringify(dist)}`);
  }

  if (valid.length > 0) {
    const avgKw =
      valid.reduce((s, r) => s + r.keyword_hit_rate, 0) / valid.length;
    const avgLat = valid.reduce((s, r) => s + r.latency_ms, 0) / valid.length;
    const lats = valid.map((r) => r.latency_ms).sort((a, b) => a - b);
    const p50 = lats[Math.floor(lats.length * 0.5)];
    const p95 = lats[Math.floor(lats.length * 0.95)];
    console.log(`Avg keyword hit:   ${Math.round(avgKw * 100)}%`);
    console.log(
      `Latency avg/P50/P95: ${Math.round(avgLat)}ms / ${p50}ms / ${p95}ms`,
    );
  }

  // Per-topic breakdown
  const topics = [...new Set(results.map((r) => r.topic))];
  if (topics.length > 1) {
    console.log("\nPer-topic breakdown:");
    for (const topic of topics) {
      const topicJudged = results.filter(
        (r) => r.topic === topic && r.relevance_score >= 0,
      );
      if (topicJudged.length === 0) continue;
      const avg =
        topicJudged.reduce((s, r) => s + r.relevance_score, 0) /
        topicJudged.length;
      console.log(
        `  ${topic.padEnd(20)} avg=${avg.toFixed(2)} n=${topicJudged.length}`,
      );
    }
  }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const questionsIdx = args.indexOf("--questions");
  const maxQuestions =
    questionsIdx >= 0 ? parseInt(args[questionsIdx + 1]) : undefined;
  const outputIdx = args.indexOf("--output");
  const outputPath = outputIdx >= 0 ? args[outputIdx + 1] : undefined;

  console.log(`VoltAgent Eval — ${maxQuestions ?? "all"} questions`);
  console.log(`Dataset: ${DATASET_PATH}\n`);

  const results = await runEval(maxQuestions);
  printSummary(results);

  const timestamp = new Date().toISOString().replace(/[:.]/g, "").slice(0, 15);
  const outFile =
    outputPath ?? path.join(RESULTS_DIR, `va_eval_${timestamp}.json`);
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, JSON.stringify(results, null, 2));
  console.log(`\nSaved: ${outFile}`);

  process.exit(0);
}

main().catch((e) => {
  console.error("Fatal:", e);
  process.exit(1);
});
