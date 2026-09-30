/** A1: which structured-output path streams partial objects with gpt-5.4-mini? */
import "./env.ts";

import { parsePartialJson } from "@langchain/core/output_parsers";
import { ChatOpenAI } from "@langchain/openai";
import { toJsonSchema } from "@langchain/core/utils/json_schema";

import { ResearchSchema } from "./graph.ts";

const model = () => new ChatOpenAI({ model: "gpt-5.4-mini", apiKey: process.env.OPENAI_API_KEY!, reasoning: { effort: "low" }, useResponsesApi: true });
const prompt = `Research "ocean tides" for a beginner: title, a 3-sentence summary, one key insight.`;

for (const method of ["functionCalling", "jsonSchema", "jsonMode"] as const) {
  try {
    const t0 = Date.now();
    let n = 0; let first = 0; let last: any;
    const s = model().withStructuredOutput(ResearchSchema, { name: "research", method });
    for await (const p of await s.stream(method === "jsonMode" ? prompt + " Reply in JSON with keys title, summary, keyInsight." : prompt)) { n++; first ||= Date.now() - t0; last = p; }
    console.log(`withStructuredOutput(${method}): ${n} partials, first at ${first}ms, total ${Date.now() - t0}ms, valid=${ResearchSchema.safeParse(last).success}`);
  } catch (e: any) { console.log(`withStructuredOutput(${method}): ERROR ${String(e.message).slice(0, 160)}`); }
}

// manual: stream raw text with a json_schema response_format, parse partial JSON ourselves
{
  const t0 = Date.now();
  let acc = ""; let n = 0; let first = 0; let last: any;
  const m = model().withConfig({ response_format: { type: "json_schema", json_schema: { name: "research", strict: true, schema: { ...(toJsonSchema(ResearchSchema) as any), additionalProperties: false } } } } as any);
  for await (const chunk of await m.stream(prompt)) {
    const text = typeof chunk.content === "string" ? chunk.content : (chunk.content as any[]).map((c) => c.text ?? "").join("");
    if (!text) continue;
    acc += text;
    const p = parsePartialJson(acc);
    if (p) { n++; first ||= Date.now() - t0; last = p; }
  }
  console.log(`raw stream + json_schema + parsePartialJson: ${n} partials, first at ${first}ms, total ${Date.now() - t0}ms, valid=${ResearchSchema.safeParse(last).success}`);
}
