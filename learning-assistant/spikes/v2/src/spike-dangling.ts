/** Does OpenAI (Responses API) reject a history with a tool call that has no result (what Stop leaves)? */
import "./env.ts";

import { AIMessage, HumanMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";

const m = new ChatOpenAI({ model: "gpt-5.4-mini", apiKey: process.env.OPENAI_API_KEY!, reasoning: { effort: "low" }, useResponsesApi: true });
try {
  await m.invoke([
    new HumanMessage("slow"),
    new AIMessage({ content: "", tool_calls: [{ id: "call_1", name: "slow", args: {}, type: "tool_call" }] }),
    new HumanMessage("hello"),
  ]);
  console.log("PASS  dangling tool call accepted by OpenAI");
} catch (e: any) {
  console.log("FAIL  dangling tool call rejected by OpenAI →", String(e.message).slice(0, 200));
}
