"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, FileSearch, LoaderCircle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { HttpError } from "@/services/http-client";
import { jobMatchService, type JobMatchReport, type MatchStatus } from "@/services/job-match-service";

const statusStyles: Record<MatchStatus, string> = {
  supported: "bg-emerald-50 text-emerald-800 border-emerald-200",
  partial: "bg-amber-50 text-amber-800 border-amber-200",
  gap: "bg-rose-50 text-rose-800 border-rose-200",
  unknown: "bg-zinc-100 text-zinc-700 border-zinc-200",
};
const statusLabels: Record<MatchStatus, string> = { supported: "Supported", partial: "Partial support", gap: "Documented gap", unknown: "Unknown" };

function errorMessage(error: unknown, uploading: boolean): string {
  if (error instanceof HttpError) {
    if (error.status === 413) return "This upload is too large. The file limit is 5 MB.";
    if (error.status === 415) return "Choose a PDF or DOCX file.";
    if (error.status === 422) return uploading
      ? "Could not extract this document. Use a text-based PDF (up to 10 pages), DOCX, or paste a shorter description."
      : "The description could not be analyzed. Use 30–8,000 characters and at most 12 distinct requirements.";
    if (error.status === 429) return "Too many requests. Please wait a minute before trying again.";
    if (error.status === 503) return "The assistant is busy or not configured yet. Please try again shortly.";
    if (error.status === 504) return "Analysis took too long. Try fewer requirements or check the local model.";
    return "The model couldn't return a verified report. Please try again or check Ollama.";
  }
  if (error instanceof DOMException && error.name === "TimeoutError") return "The request timed out. Please check the backend and try again.";
  if (error instanceof TypeError) return "Couldn't reach the backend. Check that it is running.";
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

export function JobMatch() {
  const [text, setText] = useState("");
  const [report, setReport] = useState<JobMatchReport | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<"uploading" | "analyzing" | null>(null);
  const pending = useRef<AbortController | null>(null);
  const reportRef = useRef<HTMLElement>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function run(file?: File) {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setPhase(file ? "uploading" : "analyzing");
    setError("");
    setReport(null);
    try {
      if (file) {
        const preview = await jobMatchService.extract(file, controller.signal);
        if (!controller.signal.aborted) { setText(preview.text); setWarnings(preview.warnings); }
      } else {
        const result = await jobMatchService.analyze(text, controller.signal);
        if (!controller.signal.aborted) {
          setReport(result);
          requestAnimationFrame(() => reportRef.current?.focus());
        }
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(errorMessage(cause, Boolean(file)));
    } finally {
      if (pending.current === controller) { pending.current = null; setPhase(null); }
    }
  }

  function cancel() {
    pending.current?.abort();
    pending.current = null;
    setPhase(null);
  }

  return (
    <main className="min-h-dvh bg-zinc-50/70">
      <header className="border-b bg-background px-5 py-5 sm:px-9">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2 text-sm font-medium"><ArrowLeft className="size-4" />Back to chat</Link>
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Sparkles className="size-4" />Personal Chat</span>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-5 py-10 sm:px-9 sm:py-14">
        <div className="mb-9 max-w-2xl">
          <p className="mb-3 text-xs font-medium tracking-widest text-muted-foreground uppercase">For recruiters</p>
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">Find the evidence behind the fit.</h1>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">Compare your job description with the candidate&apos;s CV and notes. Explore supported requirements, documented gaps, and the questions worth asking next.</p>
        </div>
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section aria-labelledby="input-title" className="rounded-2xl border bg-background p-5 sm:p-6">
            <h2 id="input-title" className="text-base font-semibold">1. Add your job description</h2>
            <label htmlFor="job-file" className="mt-5 block text-xs font-medium">Upload PDF or Word</label>
            <input id="job-file" type="file" accept=".pdf,.docx" disabled={Boolean(phase)} className="mt-2 w-full min-w-0 rounded-lg border p-2 text-xs file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-2 file:font-medium disabled:opacity-60" onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void run(file);
            }} />
            <p className="mt-2 text-xs leading-5 text-muted-foreground">Up to 5 MB and 10 PDF pages. Uploads are extracted temporarily and are not saved as candidate knowledge.</p>
            <label htmlFor="job-description" className="mt-6 block text-xs font-medium">2. Review the extracted text, or paste it here</label>
            <Textarea id="job-description" value={text} maxLength={8000} disabled={Boolean(phase)} placeholder="Job title, responsibilities, required skills, and preferred experience..." className="mt-2 min-h-72 resize-y bg-background text-sm leading-6" onChange={(event) => { setText(event.target.value); setReport(null); setError(""); }} />
            <p className="mt-2 text-right text-[11px] text-muted-foreground">{text.length.toLocaleString()} / 8,000 characters</p>
            {warnings.map((warning) => <p key={warning} className="mt-3 text-xs leading-5 text-muted-foreground">{warning}</p>)}
            {error && <p role="alert" className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
            <div className="mt-5 flex items-center gap-3">
              <Button disabled={Boolean(phase) || text.trim().length < 30} onClick={() => void run()} className="h-10 gap-2 px-4"><FileSearch className="size-4" />Analyze fit</Button>
              {phase && <Button variant="outline" onClick={cancel}>Cancel</Button>}
            </div>
            <p role="status" className="mt-4 text-xs leading-5 text-muted-foreground">{phase === "uploading" ? "Extracting your document..." : phase === "analyzing" ? "Extracting requirements and comparing CV evidence. Local analysis may take several minutes." : "Up to 12 distinct requirements per analysis. Missing details stay unknown."}</p>
          </section>

          <section ref={reportRef} tabIndex={-1} aria-labelledby="report-title" className="min-w-0 rounded-2xl border bg-background p-5 outline-none sm:p-6 focus-visible:ring-2 focus-visible:ring-ring">
            <h2 id="report-title" className="text-base font-semibold">{report?.jobTitle ?? "Your evidence report"}</h2>
            {!report ? <div className="flex min-h-80 flex-col items-center justify-center gap-4 px-6 text-center text-muted-foreground">
              {phase === "analyzing" ? <LoaderCircle className="size-8 motion-safe:animate-spin" aria-hidden="true" /> : <FileSearch className="size-8" aria-hidden="true" />}
              <p className="max-w-xs text-sm leading-6">{phase === "analyzing" ? "Checking each requirement against the documented experience." : "Add a job description to see the evidence, explanations, and clarification questions here."}</p>
            </div> : <>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{report.summary}</p>
              <div className="mt-5 flex flex-wrap gap-2">{(Object.keys(statusLabels) as MatchStatus[]).map((status) => <span key={status} className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${statusStyles[status]}`}>{statusLabels[status]}: {report.requirements.filter((item) => item.status === status).length}</span>)}</div>
              <div className="mt-6 space-y-5">
                {report.requirements.map((item) => <article key={item.id} className="rounded-xl border p-4 [overflow-wrap:anywhere]">
                  <div className="flex flex-wrap items-start justify-between gap-2"><h3 className="text-sm font-semibold">{item.requirement}</h3><span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusStyles[item.status]}`}>{statusLabels[item.status]}</span></div>
                  <p className="mt-2 text-[11px] font-medium text-muted-foreground">{item.importance === "unspecified" ? "Importance not specified" : item.importance === "required" ? "Required" : "Preferred"}</p>
                  <blockquote className="mt-3 border-l-2 pl-3 text-xs leading-6 text-muted-foreground">Job description: &ldquo;{item.jobExcerpt}&rdquo;</blockquote>
                  <p className="mt-3 text-sm leading-6">{item.explanation}</p>
                  {item.candidateEvidence.map((evidence, index) => <blockquote key={`${evidence.sourceId}-${index}`} className="mt-3 rounded-lg bg-zinc-50 p-3 text-xs leading-6"><p>&ldquo;{evidence.quote}&rdquo;</p><footer className="mt-1 font-medium text-muted-foreground">{evidence.source}</footer></blockquote>)}
                  {item.followUpQuestion && <p className="mt-3 text-xs leading-6"><span className="font-semibold">Ask next: </span>{item.followUpQuestion}</p>}
                </article>)}
              </div>
              <div className="mt-6 border-t pt-4">{report.limitations.map((limitation) => <p key={limitation} className="mt-2 text-[11px] leading-5 text-muted-foreground">{limitation}</p>)}</div>
            </>}
          </section>
        </div>
      </div>
    </main>
  );
}
