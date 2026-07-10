import { VoltAgent, VoltAgentObservability } from "@voltagent/core";
import { honoServer } from "@voltagent/server-hono";
import { config } from "./config";
import { supervisorAgent } from "./agents/supervisor";
import { createLangfuseProcessor } from "./tracing/langfuse-exporter";

const spanProcessors = [createLangfuseProcessor()].filter(Boolean) as import("@opentelemetry/sdk-trace-base").SpanProcessor[];

const observability = new VoltAgentObservability({
  serviceName: "career-analyst-kb",
  ...(spanProcessors.length > 0 && { spanProcessors }),
});

new VoltAgent({
  agents: { "career-lead": supervisorAgent },
  server: honoServer({ port: config.port }),
  observability,
});
