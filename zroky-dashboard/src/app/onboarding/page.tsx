"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { triggerOnboardingFailure } from "@/lib/api";
import { safeString } from "@/lib/format";
import { onboardingTriggerSchema, type OnboardingTriggerFormData } from "@/lib/schemas";

const categories = [
  "TOKEN_OVERFLOW",
  "RATE_LIMIT",
  "AUTH_FAILURE",
  "LOOP_DETECTED",
  "COST_SPIKE",
] as const;

export default function OnboardingPage() {
  const [projectName, setProjectName] = useState("zroky-prod");
  const [environment, setEnvironment] = useState("staging");
  const [status, setStatus] = useState<string>("");

  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<OnboardingTriggerFormData>({
    resolver: zodResolver(onboardingTriggerSchema),
    defaultValues: { category: "TOKEN_OVERFLOW" },
  });

  const sdkSnippet = `pip install zroky-sdk\n\nzroky init --project ${projectName} --env ${environment}\nzroky run --agent your_agent.py`;

  async function onTrigger(data: OnboardingTriggerFormData) {
    try {
      const payload = await triggerOnboardingFailure(data.category);
      setStatus(`Triggered ${payload.diagnosis_id}: ${payload.message}`);
    } catch (triggerError) {
      const message = triggerError instanceof Error ? triggerError.message : "Failed to trigger synthetic failure.";
      setStatus(message);
    }
  }

  async function onCopySnippet() {
    try {
      await navigator.clipboard.writeText(sdkSnippet);
      setStatus("SDK snippet copied.");
    } catch {
      setStatus("Clipboard not available. Copy snippet manually.");
    }
  }

  return (
    <main className="content-inner onboarding-main">
      <section className="hero panel">
        <h1>Onboarding Wizard</h1>
        <p>Three-step setup for first value: configure project, install SDK, trigger a controlled failure, and inspect fixes.</p>
      </section>

      <section className="grid-three">
        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Step 1 · Project Setup</h3>
              <p>Define project context and environment.</p>
            </div>
          </header>

          <div className="field">
            <label htmlFor="projectName">Project Name</label>
            <input id="projectName" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          </div>

          <div className="field">
            <label htmlFor="environment">Environment</label>
            <input id="environment" value={environment} onChange={(event) => setEnvironment(event.target.value)} />
          </div>
        </article>

        <article className="panel panel-muted">
          <header className="panel-header">
            <div>
              <h3>Step 2 · Install SDK</h3>
              <p>Run this command in your service repo.</p>
            </div>
          </header>

          <pre className="panel onboarding-snippet">
            {sdkSnippet}
          </pre>

          <div className="actions">
            <button type="button" className="btn btn-soft" onClick={() => void onCopySnippet()}>
              Copy Snippet
            </button>
          </div>
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <h3>Step 3 · Verify Connection</h3>
              <p>Trigger synthetic failure to validate end-to-end diagnosis.</p>
            </div>
          </header>

          <form className="list" onSubmit={handleSubmit(onTrigger)}>
            <div className="field">
              <label htmlFor="category">Failure Category</label>
              <select id="category" {...register("category")}>
                {categories.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Triggering…" : "Trigger Test Failure"}
              </button>
            </div>
          </form>
        </article>
      </section>

      <section className="panel panel-muted">
        <p className="hint">Status: {safeString(status, "Idle")}</p>
        <p className="hint">
          Next: open <Link href="/home">Home</Link>, then inspect generated issue on <Link href="/alerts">Alerts</Link> and <Link href="/calls">Calls</Link>.
        </p>
      </section>
    </main>
  );
}
