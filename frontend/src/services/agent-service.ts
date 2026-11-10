import { postJson } from "./http-client.ts";

export type AgentMessage = {
  role: "user" | "assistant";
  content: string;
};

export type SendPromptRequest = {
  conversationId: string;
  prompt: string;
  history: AgentMessage[];
};

export type SendPromptResponse = {
  content: string;
};

/** history contains prior messages; prompt is the new user message. */
async function sendPrompt(
  request: SendPromptRequest,
  { signal }: { signal?: AbortSignal } = {},
): Promise<SendPromptResponse> {
  if (!request.prompt.trim()) throw new Error("Please enter a prompt.");
  signal?.throwIfAborted();
  const baseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  // Bound the history while retaining a contiguous recent conversation.
  const history: AgentMessage[] = [];
  let characters = 0;
  for (const message of request.history.slice(-12).reverse()) {
    if (characters + message.content.length > 4000) break;
    history.unshift(message);
    characters += message.content.length;
  }
  const response = await postJson<unknown>(`${baseUrl}/api/chat`, { ...request, history }, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(130_000)]) : AbortSignal.timeout(130_000),
  });
  if (typeof response !== "object" || response === null || !("content" in response) || typeof response.content !== "string" || !response.content.trim()) {
    throw new Error("The agent returned an invalid answer.");
  }
  return { content: response.content };
}

export const agentService = { sendPrompt };
