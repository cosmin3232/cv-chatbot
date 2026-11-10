import assert from "node:assert/strict";
import { test } from "node:test";
import { agentService } from "../src/services/agent-service.ts";
import { HttpError, postJson } from "../src/services/http-client.ts";

const request = { conversationId: "test", prompt: "Hello", history: [] };

test("agent sends prompt and history to the chat API", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.ok(url.endsWith("/api/chat"));
    assert.deepEqual(JSON.parse(options.body), request);
    return Response.json({ content: "Reply" });
  });
  const response = await agentService.sendPrompt(request);
  assert.equal(typeof response.content, "string");
  assert.ok(response.content.length > 0);
});

test("agent rejects empty prompts", async () => {
  await assert.rejects(agentService.sendPrompt({ ...request, prompt: "  " }), /enter a prompt/);
});

test("agent cancels pending and already aborted requests", async (t) => {
  t.mock.method(globalThis, "fetch", (url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true });
  }));
  const controller = new AbortController();
  const pending = agentService.sendPrompt(request, { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
  await assert.rejects(agentService.sendPrompt(request, { signal: controller.signal }), { name: "AbortError" });
});

test("agent rejects malformed response data", async (t) => {
  for (const body of [null, {}, { content: " " }, { content: 42 }]) {
    t.mock.method(globalThis, "fetch", async () => Response.json(body));
    await assert.rejects(agentService.sendPrompt(request), /invalid answer/);
  }
});

test("agent limits history without changing the current prompt", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    const body = JSON.parse(options.body);
    assert.equal(body.history.length, 2);
    assert.equal(body.prompt, request.prompt);
    assert.equal(body.history.at(-1).content, "b".repeat(1500));
    return Response.json({ content: "Reply" });
  });
  await agentService.sendPrompt({ ...request, history: [
    { role: "user", content: "old".repeat(1000) },
    { role: "user", content: "a".repeat(1500) },
    { role: "assistant", content: "b".repeat(1500) },
  ] });
});

test("HTTP transport sends JSON and forwards the abort signal", async (t) => {
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/agent");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.equal(options.signal, controller.signal);
    assert.deepEqual(JSON.parse(options.body), request);
    return Response.json({ content: "Reply" });
  });
  assert.deepEqual(await postJson("/api/agent", request, { signal: controller.signal }), { content: "Reply" });
});

test("HTTP transport rejects non-success statuses", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 503 }));
  await assert.rejects(postJson("/api/agent", request), (error) => error instanceof HttpError && error.status === 503);
});

test("HTTP transport propagates network failures", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Network failure"); });
  await assert.rejects(postJson("/api/agent", request), /Network failure/);
});
