import assert from "node:assert/strict";
import { test } from "node:test";
import { jobMatchService, parseJobMatchReport } from "../src/services/job-match-service.ts";

const description = "Python Backend Engineer. Required: experience developing Python APIs.";
const report = () => ({
  jobTitle: "Python Backend Engineer", summary: "One requirement is supported.",
  requirements: [{ id: "req-1", requirement: "Python APIs", importance: "required", jobExcerpt: "experience developing Python APIs", status: "supported",
    candidateEvidence: [{ sourceId: "source-1", source: "CV, page 1", quote: "Built Python APIs with FastAPI." }],
    explanation: "The candidate built Python APIs.", followUpQuestion: null }],
  strengths: ["req-1"], gaps: [], questions: [], limitations: ["Human review is required."],
});

test("job analysis sends only reviewed job text and parses report evidence", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.ok(url.endsWith("/api/job-match"));
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), { jobDescription: description });
    return Response.json(report());
  });
  assert.deepEqual(await jobMatchService.analyze(description), report());
});

test("invalid job text is rejected without a request", async (t) => {
  t.mock.method(globalThis, "fetch", () => assert.fail("Unexpected request"));
  await assert.rejects(jobMatchService.analyze("short"), /30/);
  await assert.rejects(jobMatchService.analyze("x".repeat(8001)), /8,000/);
});

test("malformed report entries and dangling references are rejected", () => {
  for (const value of [null, {}, { ...report(), requirements: [] }]) {
    assert.throws(() => parseJobMatchReport(value), /invalid/);
  }
  const invalidEvidence = report();
  invalidEvidence.requirements[0].candidateEvidence[0].quote = 10;
  assert.throws(() => parseJobMatchReport(invalidEvidence), /invalid/);
  const invalidStatus = report();
  invalidStatus.requirements[0].status = "hire";
  assert.throws(() => parseJobMatchReport(invalidStatus), /invalid/);
  const invalidReferences = report();
  invalidReferences.gaps = ["req-99"];
  assert.throws(() => parseJobMatchReport(invalidReferences), /references/);
});

test("upload uses multipart data without forcing a JSON content type", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.ok(url.endsWith("/api/job-description/extract"));
    assert.ok(options.body instanceof FormData);
    assert.equal(options.body.get("file").name, "job.docx");
    assert.equal(options.headers, undefined);
    return Response.json({ text: description, warnings: ["Review the text."] });
  });
  const preview = await jobMatchService.extract(new File(["test"], "job.docx"));
  assert.equal(preview.text, description);
});

test("unsupported and oversized files are rejected before upload", async (t) => {
  t.mock.method(globalThis, "fetch", () => assert.fail("Unexpected request"));
  await assert.rejects(jobMatchService.extract(new File(["test"], "bad.exe")), /PDF/);
  await assert.rejects(jobMatchService.extract(new File([], "empty.pdf")), /nonempty/);
  await assert.rejects(jobMatchService.extract(new File([new Uint8Array(5 * 1024 * 1024 + 1)], "large.pdf")), /5 MB/);
});

test("analysis cancellation propagates to the request", async (t) => {
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", (url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true });
  }));
  const pending = jobMatchService.analyze(description, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});

test("backend errors and invalid upload previews propagate", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 429 }));
  await assert.rejects(jobMatchService.analyze(description), (error) => error.status === 429);
  t.mock.method(globalThis, "fetch", async () => Response.json({ text: "", warnings: [] }));
  await assert.rejects(jobMatchService.extract(new File(["test"], "job.pdf")), /invalid document preview/);
});
