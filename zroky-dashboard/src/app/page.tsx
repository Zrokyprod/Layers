import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Zroky Dashboard",
  description: "Mission control for protected agent actions, approvals, outcomes, evidence, and workspace controls.",
};

export default function HomePage() {
  redirect("/home");
}
