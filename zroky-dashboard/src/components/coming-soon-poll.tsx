"use client";

/**
 * <ComingSoonPoll> — Module 9 smoke-test voting widget.
 *
 * Renders a "🔒 Coming soon" feature card with a 👍 / 👎 poll.
 * Users vote on whether they'd use the feature when it ships.
 * Their vote is upserted to /v1/feature-interest and shown read-only
 * after submission (with a "Change vote" affordance).
 *
 * Designed to be reusable for ANY future coming-soon feature: pass
 * `featureKey`, `title`, `description`, and (optionally) a tailored
 * `useCasePrompt` shown when the user votes "interested".
 *
 * No vote counts are exposed to the customer (decision: don't bias
 * via herd / social-proof signal). Aggregates are viewed in the
 * standalone zroky-admin feature-votes page or via the CLI viewer.
 */

import { useCallback, useEffect, useState } from "react";

import { getMyFeatureVote, submitFeatureVote } from "@/lib/api";
import type { FeatureVoteResponse, FeatureVoteValue } from "@/lib/types";
import { Button } from "@/components/ui/button";

type ComingSoonPollProps = {
  featureKey: string;
  title: string;
  description: string;
  /** Prompt shown above the use-case textarea after voting 'interested'. */
  useCasePrompt?: string;
  /** Optional className to merge with the outer container. */
  className?: string;
};

const DEFAULT_USE_CASE_PROMPT =
  "What's the #1 fix you'd want auto-applied? (helps us build the right thing first)";

export function ComingSoonPoll({
  featureKey,
  title,
  description,
  useCasePrompt = DEFAULT_USE_CASE_PROMPT,
  className,
}: ComingSoonPollProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [existing, setExisting] = useState<FeatureVoteResponse | null>(null);
  const [editing, setEditing] = useState<boolean>(false);
  const [pendingVote, setPendingVote] = useState<FeatureVoteValue | null>(null);
  const [useCaseInput, setUseCaseInput] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [thanksMessage, setThanksMessage] = useState<string | null>(null);

  // Load the current user's vote on mount.
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getMyFeatureVote(featureKey, controller.signal)
      .then((row) => {
        setExisting(row);
        setPendingVote(row.vote);
        setUseCaseInput(row.use_case ?? "");
      })
      .catch(() => {
        // 404 → no vote yet (expected, common case). Other errors:
        // silently let the form render in "not voted yet" state —
        // the user can still try to submit and surface the error then.
        setExisting(null);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [featureKey]);

  const handleSubmit = useCallback(async () => {
    if (!pendingVote) {
      setError("Pick 👍 or 👎 first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const row = await submitFeatureVote({
        feature_key: featureKey,
        vote: pendingVote,
        use_case:
          pendingVote === "interested" && useCaseInput.trim()
            ? useCaseInput.trim()
            : null,
      });
      setExisting(row);
      setEditing(false);
      setThanksMessage(
        pendingVote === "interested"
          ? "Got it — we'll DM you when it ships."
          : "Thanks — we hear you.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record vote.");
    } finally {
      setSubmitting(false);
    }
  }, [featureKey, pendingVote, useCaseInput]);

  const showForm = !loading && (existing === null || editing);
  const showVoted = !loading && existing !== null && !editing;

  return (
    <div
      className={`rounded-xl border border-dashed bg-muted/30 p-6 ${className ?? ""}`}
      data-testid="coming-soon-poll"
      data-feature-key={featureKey}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold leading-none tracking-tight">{title}</h3>
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
          <LockIcon /> Coming soon
        </span>
      </header>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>

      {loading ? (
        <p className="mt-4 text-sm text-muted-foreground" aria-live="polite">
          Loading…
        </p>
      ) : null}

      {showForm ? (
        <div className="mt-4 space-y-3">
          <p className="text-sm font-medium">Would you turn this on if available?</p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={pendingVote === "interested" ? "default" : "outline"}
              size="sm"
              onClick={() => setPendingVote("interested")}
              disabled={submitting}
              aria-pressed={pendingVote === "interested"}
            >
              👍 Yes, I&apos;d try it
            </Button>
            <Button
              variant={pendingVote === "not_interested" ? "default" : "outline"}
              size="sm"
              onClick={() => setPendingVote("not_interested")}
              disabled={submitting}
              aria-pressed={pendingVote === "not_interested"}
            >
              👎 Not yet — I&apos;d want more trust first
            </Button>
          </div>

          {pendingVote === "interested" ? (
            <div className="space-y-1.5">
              <label
                htmlFor={`use-case-${featureKey}`}
                className="block text-xs font-medium text-muted-foreground"
              >
                {useCasePrompt}
              </label>
              <textarea
                id={`use-case-${featureKey}`}
                value={useCaseInput}
                onChange={(event) => setUseCaseInput(event.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
                rows={2}
                maxLength={2000}
                disabled={submitting}
                placeholder="(optional — your answer shapes what we build)"
              />
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => void handleSubmit()}
              disabled={submitting || !pendingVote}
            >
              {submitting ? "Saving…" : existing ? "Update vote" : "Save vote"}
            </Button>
            {existing && editing ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing(false);
                  setPendingVote(existing.vote);
                  setUseCaseInput(existing.use_case ?? "");
                  setError(null);
                }}
                disabled={submitting}
              >
                Cancel
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {showVoted && existing ? (
        <div className="mt-4 space-y-2 rounded-md border border-border bg-background/60 p-3">
          <p className="text-sm">
            {existing.vote === "interested" ? "👍" : "👎"}{" "}
            <span className="font-medium">
              You voted:{" "}
              {existing.vote === "interested" ? "Interested" : "Not yet interested"}
            </span>
            {thanksMessage ? (
              <span className="text-muted-foreground"> — {thanksMessage}</span>
            ) : null}
          </p>
          {existing.use_case ? (
            <p className="text-xs italic text-muted-foreground">
              &ldquo;{existing.use_case}&rdquo;
            </p>
          ) : null}
          <button
            type="button"
            onClick={() => {
              setEditing(true);
              setThanksMessage(null);
            }}
            className="text-xs font-medium text-primary underline-offset-4 hover:underline"
          >
            Change vote
          </button>
        </div>
      ) : null}
    </div>
  );
}

function LockIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}
