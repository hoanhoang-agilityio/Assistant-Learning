import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Loads apps/web/.env without printing values. Tracing off unless a spike asks.
const envPath = fileURLToPath(new URL("../../../apps/web/.env", import.meta.url));
for (const line of readFileSync(envPath, "utf8").split("\n")) {
  const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
  if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2];
}
process.env.LANGSMITH_TRACING = "false";
process.env.LANGCHAIN_TRACING_V2 = "false";

export const DB_URL = "postgres://spike@localhost:55432/spikes";
