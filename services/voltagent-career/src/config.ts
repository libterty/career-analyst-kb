import { createOpenAI } from "@ai-sdk/openai";
import dotenv from "dotenv";
import path from "node:path";

const ROOT_ENV_PATH = path.resolve(__dirname, "../../../.env");
const LOCAL_ENV_PATH = path.resolve(__dirname, "../.env");

dotenv.config({ path: ROOT_ENV_PATH });
dotenv.config({ path: LOCAL_ENV_PATH, override: false });

function required(...keys: string[]): string {
  for (const key of keys) {
    const val = process.env[key];
    if (val) return val;
  }
  throw new Error(`Missing required env var: ${keys.join(" or ")}`);
}

function normalizeOllamaBaseUrl(url: string): string {
  return url.endsWith("/v1") ? url : `${url.replace(/\/+$/, "")}/v1`;
}

export const config = {
  kbApiUrl: process.env.KB_API_URL ?? "http://localhost:8000",
  kbApiToken: required("CAREER_API_TOKEN", "KB_API_TOKEN"),
  ollamaBaseUrl: normalizeOllamaBaseUrl(
    process.env.OLLAMA_BASE_URL ?? "http://localhost:11434",
  ),
  voltagentModel: process.env.VOLTAGENT_MODEL ?? "gemma3:12b",
  port: parseInt(process.env.PORT ?? "3141", 10),
} as const;

// Use .chat() accessor to force /v1/chat/completions endpoint.
// @ai-sdk/openai v3 default provider() uses the Responses API (/v1/responses)
// which Ollama does not support.
const _ollama = createOpenAI({
  baseURL: config.ollamaBaseUrl,
  apiKey: "ollama",
});

export const ollamaModel = _ollama.chat(config.voltagentModel);
