import { VoltAgent } from "@voltagent/core";
import { honoServer } from "@voltagent/server-hono";
import { config } from "./config";
import { supervisorAgent } from "./agents/supervisor";

new VoltAgent({
  agents: { "career-lead": supervisorAgent },
  server: honoServer({ port: config.port }),
});
