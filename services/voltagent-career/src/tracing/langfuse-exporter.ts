import type { SpanProcessor } from "@opentelemetry/sdk-trace-base";

/**
 * Returns a Langfuse BatchSpanProcessor when LANGFUSE_PUBLIC_KEY and
 * LANGFUSE_SECRET_KEY are present; returns null otherwise so the rest of
 * startup works normally without Langfuse configured.
 */
export function createLangfuseProcessor(): SpanProcessor | null {
  const publicKey = process.env.LANGFUSE_PUBLIC_KEY;
  const secretKey = process.env.LANGFUSE_SECRET_KEY;

  if (!publicKey || !secretKey) return null;

  // Lazy import so the package is only required when keys are present.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { createLangfuseSpanProcessor } = require("@voltagent/langfuse-exporter") as typeof import("@voltagent/langfuse-exporter");

  return createLangfuseSpanProcessor({
    publicKey,
    secretKey,
    baseUrl: process.env.LANGFUSE_BASE_URL,
  });
}
