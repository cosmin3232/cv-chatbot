import type { Metadata } from "next";
import { JobMatch } from "@/components/job-match";

export const metadata: Metadata = {
  title: "Job fit analysis | Personal Chat",
  description: "Compare job requirements with documented CV experience and review the evidence.",
};

export default function JobMatchPage() {
  return <JobMatch />;
}
