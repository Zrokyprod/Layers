"use client";

import { useEffect, useState } from "react";
import { getSharedDiagnosis } from "@/lib/api";
import type { DiagnosisShareReadResponse } from "@/lib/types";

interface Props {
  params: { token: string };
}

type LoadState =
  | { status: "loading" }
  | { status: "ok"; data: DiagnosisShareReadResponse }
  | { status: "expired" }
  | { status: "error"; message: string };

function SeverityBadge({ severity }: { severity?: string }) {
  const color: Record<string, string> = {
    critical: "bg-red-100 text-red-700",
    high: "bg-orange-100 text-orange-700",
    medium: "bg-yellow-100 text-yellow-700",
    low: "bg-green-100 text-green-700",
  };
  const cls = color[(severity ?? "").toLowerCase()] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {severity ?? "unknown"}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color: Record<string, string> = {
    pending: "bg-gray-100 text-gray-700",
    running: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
  };
  const cls = color[status] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}

function ResultPanel({ result }: { result: Record<string, unknown> }) {
  const { category, severity, root_cause, fix_suggestions, summary } = result as {
    category?: string;
    severity?: string;
    root_cause?: string;
    fix_suggestions?: string[];
    summary?: string;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        {category && (
          <span className="inline-flex items-center rounded-full bg-purple-100 text-purple-700 px-2.5 py-0.5 text-xs font-semibold">
            {category}
          </span>
        )}
        {severity && <SeverityBadge severity={severity} />}
      </div>

      {summary && (
        <p className="text-sm text-gray-700">{summary}</p>
      )}

      {root_cause && (
        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Root Cause</h3>
          <p className="text-sm text-gray-700 bg-gray-50 rounded p-3">{root_cause}</p>
        </div>
      )}

      {Array.isArray(fix_suggestions) && fix_suggestions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Fix Suggestions</h3>
          <ul className="space-y-2">
            {fix_suggestions.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-gray-700">
                <span className="mt-0.5 shrink-0 text-green-500">✓</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-gray-500 hover:text-gray-700">Raw JSON</summary>
        <pre className="mt-2 overflow-auto rounded bg-gray-50 p-3 text-gray-600">
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export default function DiagnosisSharePage({ params }: Props) {
  const { token } = params;
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getSharedDiagnosis(token)
      .then((data) => {
        if (!cancelled) setState({ status: "ok", data });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        const msg = err.message ?? "";
        if (msg.includes("410") || msg.includes("expired") || msg.includes("revoked")) {
          setState({ status: "expired" });
        } else {
          setState({ status: "error", message: msg });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="mx-auto max-w-2xl">
        {/* Header */}
        <div className="mb-8 flex items-center gap-3">
          <div className="size-8 rounded-lg bg-indigo-600 flex items-center justify-center">
            <span className="text-white text-sm font-bold">Z</span>
          </div>
          <span className="text-lg font-semibold text-gray-900">Zroky AI</span>
          <span className="ml-auto inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
            Read-only view
          </span>
        </div>

        {/* Card */}
        <div className="rounded-xl bg-white shadow-sm ring-1 ring-gray-200 overflow-hidden">
          {state.status === "loading" && (
            <div className="p-10 text-center text-gray-500 text-sm">Loading diagnosis…</div>
          )}

          {state.status === "expired" && (
            <div className="p-10 text-center">
              <div className="text-4xl mb-3">🔒</div>
              <h2 className="text-base font-semibold text-gray-800">This link has expired or been revoked</h2>
              <p className="mt-1 text-sm text-gray-500">Please ask the owner to share a new link.</p>
            </div>
          )}

          {state.status === "error" && (
            <div className="p-10 text-center">
              <div className="text-4xl mb-3">⚠️</div>
              <h2 className="text-base font-semibold text-gray-800">Unable to load diagnosis</h2>
              <p className="mt-1 text-sm text-gray-500">{state.message}</p>
            </div>
          )}

          {state.status === "ok" && (
            <>
              <div className="border-b border-gray-100 px-6 py-4 flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <h1 className="text-base font-semibold text-gray-900">Shared Diagnosis</h1>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Diagnosis ID: <code className="font-mono">{state.data.diagnosis_id}</code>
                  </p>
                </div>
                <StatusBadge status={state.data.status} />
              </div>

              <div className="px-6 py-5">
                {state.data.status === "completed" && state.data.result_json ? (
                  <ResultPanel result={JSON.parse(state.data.result_json) as Record<string, unknown>} />
                ) : state.data.status === "failed" ? (
                  <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
                    <strong>Diagnosis failed:</strong> {state.data.error_message ?? "Unknown error"}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">
                    Diagnosis is {state.data.status}. Check back shortly.
                  </p>
                )}
              </div>

              <div className="border-t border-gray-100 bg-gray-50 px-6 py-3 flex items-center justify-between text-xs text-gray-400">
                <span>Shared via Zroky AI</span>
                {state.data.expires_at && (
                  <span>Expires {new Date(state.data.expires_at).toLocaleDateString()}</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
