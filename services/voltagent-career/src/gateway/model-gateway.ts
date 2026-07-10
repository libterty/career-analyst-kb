/**
 * Model Gateway — single source of truth for task→model assignment.
 *
 * Task tiers:
 *   supervisor  Heavy reasoning, multi-agent orchestration  → VOLTAGENT_MODEL  (default: gemma3:12b)
 *   specialist  Domain-specific sub-agents                 → SPECIALIST_MODEL  (default: VOLTAGENT_MODEL)
 *   judge       Answer quality scoring, lightweight eval   → JUDGE_MODEL       (default: qwen3:8b)
 *   fast        Quick lookups, intent detection            → FAST_MODEL        (default: qwen3:4b)
 *
 * All env vars fall back gracefully so the system runs with a single model.
 */
import { createOpenAI } from "@ai-sdk/openai";
import { config } from "../config";

function makeOllamaProvider(baseUrl: string) {
  return createOpenAI({ baseURL: baseUrl, apiKey: "ollama" });
}

const ollama = makeOllamaProvider(config.ollamaBaseUrl);

function resolveModel(envKey: string, fallback: string) {
  return (process.env[envKey] ?? fallback).trim();
}

const supervisorModelId  = resolveModel("VOLTAGENT_MODEL",  "gemma3:12b");
const specialistModelId  = resolveModel("SPECIALIST_MODEL", supervisorModelId);
const judgeModelId       = resolveModel("JUDGE_MODEL",      "qwen3:8b");
const fastModelId        = resolveModel("FAST_MODEL",       "qwen3:4b");

/** Heavy orchestration — supervisor agent */
export const supervisorModel  = ollama.chat(supervisorModelId);

/** Domain reasoning — resume, interview, career-plan, salary agents */
export const specialistModel  = ollama.chat(specialistModelId);

/** Quality scoring — answer-quality judge middleware */
export const judgeModel       = ollama.chat(judgeModelId);

/** Lightweight inference — intent detection, quick lookups */
export const fastModel        = ollama.chat(fastModelId);

export const modelGateway = {
  supervisor:  supervisorModel,
  specialist:  specialistModel,
  judge:       judgeModel,
  fast:        fastModel,
} as const;

export type ModelTier = keyof typeof modelGateway;
