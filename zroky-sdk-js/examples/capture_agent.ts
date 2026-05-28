import OpenAI from "openai";
import { captureRetrieval, init, trace, wrap } from "@zroky/sdk";

init({
  projectId: process.env.ZROKY_PROJECT_ID,
  apiKey: process.env.ZROKY_API_KEY,
});

const openai = wrap(new OpenAI(), {
  agentName: "refund-agent",
  workflowId: "refund-review",
  environment: "production",
});

const runRefundReview = trace(async (input: string) => {
  const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: input }],
  });

  await captureRetrieval({
    query: "refund policy",
    indexName: "support-kb",
    documents: [{ id: "policy_v11", score: 0.91, title: "Refunds" }],
    parentCallId: response._zroky_call_id,
  });

  return response;
}, { agentName: "refund-agent", workflowId: "refund-review" });

await runRefundReview("Customer wants refund after delayed delivery.");
