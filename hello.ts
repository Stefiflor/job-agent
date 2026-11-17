import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const m of query({ prompt: "Respondé solo: OK" })) {
  if (m.type === "system" && m.subtype === "init") {
    console.log("auth:", m.apiKeySource);
  }
  if (m.type === "result") {
    console.log(m.subtype, "→", m.result);
  }
}
