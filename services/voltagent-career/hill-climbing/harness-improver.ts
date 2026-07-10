/**
 * Phase C-2 — Harness Improver
 *
 * Reads the latest trace analysis (eval/results/trace_analysis_latest.json)
 * and the current supervisor routing instructions, then asks an LLM to propose
 * targeted prompt diffs.  Each diff is classified as:
 *
 *   low_risk  — adds/sharpens example keywords, clarifies existing rules
 *   high_risk — restructures routing logic, adds/removes route targets
 *
 * Output:
 *   hill-climbing/proposed-diffs/YYYYMMDD_HHMMSS.json
 *   hill-climbing/proposed-diffs/latest.json
 *
 * Usage:
 *   npx tsx services/voltagent-career/hill-climbing/harness-improver.ts
 *   npx tsx services/voltagent-career/hill-climbing/harness-improver.ts --dry-run
 */

import fs from "node:fs";
import path from "node:path";
import { generateText, Output } from "ai";
import { z } from "zod";
import { supervisorModel } from "../src/gateway/model-gateway";

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const REPO_ROOT = path.resolve(__dirname, "../../..");
const TRACE_ANALYSIS_PATH = path.join(
  REPO_ROOT,
  "eval/results/trace_analysis_latest.json",
);
const SUPERVISOR_PATH = path.join(__dirname, "../src/agents/supervisor.ts");
const DIFFS_DIR = path.join(__dirname, "proposed-diffs");

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const DiffSchema = z.object({
  id: z.string().describe("Short slug, e.g. 'clarify-career-plan-keywords'"),
  risk: z.enum(["low_risk", "high_risk"]),
  target_category: z.string().describe("Which routing category this addresses"),
  rationale: z.string().describe("Why this change should improve routing"),
  original_excerpt: z
    .string()
    .describe("The exact excerpt from the current instructions to replace"),
  replacement: z
    .string()
    .describe("The replacement text (same or shorter preferred)"),
});

const ProposedDiffsSchema = z.object({
  diffs: z.array(DiffSchema).min(0).max(10),
  summary: z
    .string()
    .describe("One-paragraph summary of the proposed improvements"),
});

type Diff = z.infer<typeof DiffSchema>;
type ProposedDiffs = z.infer<typeof ProposedDiffsSchema>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractInstructions(supervisorSource: string): string {
  const match = supervisorSource.match(/instructions:\s*`([\s\S]*?)`/);
  if (!match) {
    throw new Error(
      "Could not locate `instructions` template literal in supervisor.ts",
    );
  }
  return match[1].trim();
}

function loadTraceAnalysis(): Record<string, unknown> {
  if (!fs.existsSync(TRACE_ANALYSIS_PATH)) {
    throw new Error(
      `Trace analysis not found at ${TRACE_ANALYSIS_PATH}\n` +
        "Run: python eval/trace_analyzer.py",
    );
  }
  return JSON.parse(fs.readFileSync(TRACE_ANALYSIS_PATH, "utf8"));
}

function buildPrompt(
  currentInstructions: string,
  traceAnalysis: Record<string, unknown>,
): string {
  const hillTargets = (traceAnalysis.hill_targets as unknown[]) ?? [];
  const confusionPairs = (traceAnalysis.confusion_pairs as unknown[]) ?? [];
  const nearMisses = (traceAnalysis.near_misses as unknown[]) ?? [];
  const accuracy = traceAnalysis.overall_accuracy as number;

  const targetsText =
    hillTargets.length > 0
      ? JSON.stringify(hillTargets, null, 2)
      : "None — routing is currently 100% accurate.";

  const confusionText =
    confusionPairs.length > 0
      ? JSON.stringify(confusionPairs.slice(0, 10), null, 2)
      : "None.";

  const nearMissText =
    nearMisses.length > 0
      ? JSON.stringify(nearMisses.slice(0, 10), null, 2)
      : "None.";

  return `You are a prompt-engineering specialist tasked with improving an LLM routing classifier.

## Current Routing Instructions
\`\`\`
${currentInstructions}
\`\`\`

## Trace Analysis (overall accuracy: ${(accuracy * 100).toFixed(1)}%)

### Hill-climbing Targets
${targetsText}

### Confusion Pairs (wrong predictions)
${confusionText}

### Near-misses (correct but low-confidence, threshold=${0.75})
${nearMissText}

## Your Task
Propose up to 5 targeted edits to the routing instructions above.

### Diff Classification Rules
- **low_risk**: Adds specific Chinese keywords/examples to an existing route, clarifies ambiguity between two similar categories, or tightens a description WITHOUT changing which routes exist.
- **high_risk**: Changes route names, adds or removes route targets, restructures the overall logic flow.

### Constraints
- Each diff must supply an exact \`original_excerpt\` string that appears verbatim in the instructions (so it can be applied with string-replace).
- Keep \`replacement\` roughly the same length — do not bloat the prompt.
- If routing is already 100% accurate and near-misses are few, you may return 0–2 minor confidence-hardening diffs or an empty array.
- Output valid JSON matching the schema exactly.`;
}

// ---------------------------------------------------------------------------
// Core
// ---------------------------------------------------------------------------

async function generateDiffs(
  currentInstructions: string,
  traceAnalysis: Record<string, unknown>,
): Promise<ProposedDiffs> {
  const prompt = buildPrompt(currentInstructions, traceAnalysis);

  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore — AI SDK v6 Output.object causes TS2589 deep type recursion; runtime is correct
  const result = await generateText({
    model: supervisorModel,
    output: Output.object({ schema: ProposedDiffsSchema }),
    prompt,
  });

  return result.output as ProposedDiffs;
}

function applyDryRun(instructions: string, diffs: Diff[]): void {
  let patched = instructions;
  let applied = 0;
  for (const diff of diffs) {
    if (patched.includes(diff.original_excerpt)) {
      patched = patched.replace(diff.original_excerpt, diff.replacement);
      applied++;
      console.log(`  [OK] ${diff.id} (${diff.risk})`);
    } else {
      console.log(
        `  [MISS] ${diff.id} — excerpt not found in current instructions`,
      );
    }
  }
  console.log(
    `\nDry-run: ${applied}/${diffs.length} diffs would apply cleanly.`,
  );
  if (applied > 0) {
    console.log("\n--- Patched instructions preview ---");
    console.log(
      patched.slice(0, 600) + (patched.length > 600 ? "\n... (truncated)" : ""),
    );
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const isDryRun = process.argv.includes("--dry-run");

  console.log("=== Harness Improver ===\n");

  const supervisorSource = fs.readFileSync(SUPERVISOR_PATH, "utf8");
  const currentInstructions = extractInstructions(supervisorSource);
  console.log(
    `Loaded supervisor instructions (${currentInstructions.length} chars)`,
  );

  const traceAnalysis = loadTraceAnalysis();
  const rows = (traceAnalysis.total_rows as number) ?? 0;
  const acc = ((traceAnalysis.overall_accuracy as number) ?? 0) * 100;
  console.log(`Trace analysis: ${rows} rows, ${acc.toFixed(1)}% accuracy`);

  console.log("\nGenerating diff proposals via LLM ...");
  const proposed = await generateDiffs(currentInstructions, traceAnalysis);

  console.log(`\nProposed ${proposed.diffs.length} diff(s):`);
  for (const diff of proposed.diffs) {
    console.log(
      `  [${diff.risk.padEnd(9)}] ${diff.id} — ${diff.rationale.slice(0, 70)}`,
    );
  }

  const lowRiskCount = proposed.diffs.filter(
    (d) => d.risk === "low_risk",
  ).length;
  const highRiskCount = proposed.diffs.filter(
    (d) => d.risk === "high_risk",
  ).length;
  console.log(`\n  low_risk: ${lowRiskCount}  high_risk: ${highRiskCount}`);
  console.log(`\nSummary: ${proposed.summary}`);

  if (isDryRun) {
    console.log("\n--- Dry run: checking if excerpts match ---");
    applyDryRun(currentInstructions, proposed.diffs);
    return;
  }

  // Persist
  fs.mkdirSync(DIFFS_DIR, { recursive: true });
  const ts = new Date()
    .toISOString()
    .replace(/[:.]/g, "")
    .replace("T", "_")
    .slice(0, 15);
  const outPath = path.join(DIFFS_DIR, `${ts}.json`);
  const latestPath = path.join(DIFFS_DIR, "latest.json");

  const output = {
    generated_at: new Date().toISOString(),
    supervisor_path: SUPERVISOR_PATH,
    trace_analysis_path: TRACE_ANALYSIS_PATH,
    overall_accuracy: traceAnalysis.overall_accuracy,
    summary: proposed.summary,
    diffs: proposed.diffs,
  };

  fs.writeFileSync(outPath, JSON.stringify(output, null, 2));
  fs.writeFileSync(latestPath, JSON.stringify(output, null, 2));

  console.log(`\nDiffs saved to ${outPath}`);
  console.log(`Latest:         ${latestPath}`);

  if (lowRiskCount > 0) {
    console.log(`\n${lowRiskCount} low-risk diff(s) ready to auto-apply:`);
    console.log("  python eval/apply_low_risk_diffs.py");
  } else {
    console.log("\nNo low-risk diffs — nothing to auto-apply.");
  }
}

main().catch((err) => {
  console.error("Harness improver failed:", err);
  process.exit(1);
});
