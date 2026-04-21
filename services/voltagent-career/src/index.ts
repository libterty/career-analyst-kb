import { VoltAgent } from "@voltagent/core";
import { config } from "./config";
import { supervisorAgent } from "./agents/supervisor";

new VoltAgent({
  agents: { "career-lead": supervisorAgent },
  port: config.port,
});
