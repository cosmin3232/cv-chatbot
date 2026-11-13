import { HttpError, postJson } from "./http-client.ts";

export type MatchStatus = "supported" | "partial" | "gap" | "unknown";
export type RequirementAssessment = {
  id: string;
  requirement: string;
  importance: "required" | "preferred" | "unspecified";
  jobExcerpt: string;
  status: MatchStatus;
  candidateEvidence: { sourceId: string; source: string; quote: string }[];
  explanation: string;
  followUpQuestion: string | null;
};
export type JobMatchReport = {
  jobTitle: string | null;
  summary: string;
  requirements: RequirementAssessment[];
  strengths: string[];
  gaps: string[];
  questions: string[];
  limitations: string[];
};

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const isText = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const isStrings = (value: unknown): value is string[] => Array.isArray(value) && value.every(isText);

export function parseJobMatchReport(value: unknown): JobMatchReport {
  if (!isObject(value) || !(value.jobTitle === null || isText(value.jobTitle)) || !isText(value.summary) ||
      !isStrings(value.strengths) || !isStrings(value.gaps) || !isStrings(value.questions) || !isStrings(value.limitations) ||
      !Array.isArray(value.requirements) || !value.requirements.length || value.requirements.length > 12) {
    throw new Error("The server returned an invalid report.");
  }
  for (const item of value.requirements) {
    if (!isObject(item) || !isText(item.id) || !isText(item.requirement) || !isText(item.jobExcerpt) || !isText(item.explanation) ||
        !["required", "preferred", "unspecified"].includes(String(item.importance)) ||
        !["supported", "partial", "gap", "unknown"].includes(String(item.status)) ||
        !(item.followUpQuestion === null || isText(item.followUpQuestion)) || !Array.isArray(item.candidateEvidence) ||
        !item.candidateEvidence.every((evidence) => isObject(evidence) && isText(evidence.sourceId) && isText(evidence.source) && isText(evidence.quote))) {
      throw new Error("The server returned an invalid requirement assessment.");
    }
  }
  const ids = value.requirements.map((item) => item.id);
  if (new Set(ids).size !== ids.length || [...value.strengths, ...value.gaps].some((id) => !ids.includes(id))) {
    throw new Error("The server returned invalid requirement references.");
  }
  return value as JobMatchReport;
}

const apiUrl = () => (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const withTimeout = (signal: AbortSignal | undefined, milliseconds: number) => signal
  ? AbortSignal.any([signal, AbortSignal.timeout(milliseconds)]) : AbortSignal.timeout(milliseconds);

async function analyze(jobDescription: string, signal?: AbortSignal): Promise<JobMatchReport> {
  const text = jobDescription.trim();
  if (text.length < 30 || text.length > 8000) throw new Error("Use a job description between 30 and 8,000 characters.");
  return parseJobMatchReport(await postJson<unknown>(`${apiUrl()}/api/job-match`, { jobDescription: text }, {
    signal: withTimeout(signal, 250_000),
  }));
}

async function extract(file: File, signal?: AbortSignal): Promise<{ text: string; warnings: string[] }> {
  if (!/\.(pdf|docx)$/i.test(file.name)) throw new Error("Choose a PDF or DOCX file.");
  if (file.size === 0 || file.size > 5 * 1024 * 1024) throw new Error("Choose a nonempty file no larger than 5 MB.");
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${apiUrl()}/api/job-description/extract`, {
    method: "POST", body: form, signal: withTimeout(signal, 60_000),
  });
  if (!response.ok) throw new HttpError(response.status, `Upload failed (${response.status}).`);
  const result: unknown = await response.json();
  if (!isObject(result) || !isText(result.text) || result.text.length > 8000 || !isStrings(result.warnings)) {
    throw new Error("The server returned an invalid document preview.");
  }
  return { text: result.text, warnings: result.warnings };
}

export const jobMatchService = { analyze, extract };
