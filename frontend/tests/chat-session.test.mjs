import assert from "node:assert/strict";
import { test } from "node:test";
import { createConversation } from "../src/services/chat-session.ts";
import { agentService } from "../src/services/agent-service.ts";

test("each new conversation/session has its own UUID and isolated messages", () => {
  const sessions = Array.from({ length: 100 }, () => createConversation());
  assert.equal(new Set(sessions.map((session) => session.id)).size, 100);
  for (const session of sessions) {
    assert.match(session.id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  }
  sessions[0].messages.push({ id: crypto.randomUUID(), role: "user", content: "Hello" });
  assert.equal(sessions[1].messages.length, 0);
});

test("multiple prompts retain the conversation UUID and distinct message IDs", async (t) => {
  const session = createConversation();
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push(JSON.parse(options.body));
    return Response.json({ content: "Reply" });
  });
  for (const prompt of ["Hello", "What experience?"]) {
    await agentService.sendPrompt({ conversationId: session.id, messageId: crypto.randomUUID(), prompt, history: [] });
  }
  assert.ok(requests.every((request) => request.conversationId === session.id));
  assert.notEqual(requests[0].messageId, requests[1].messageId);
  assert.notEqual(createConversation().id, session.id);
});
