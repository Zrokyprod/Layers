import type { SetupReadiness, SetupState } from "@/lib/setup-readiness";

export type SetupFlowTone = "success" | "warning" | "danger" | "neutral" | "setup";

export type SetupFlowMetric = {
  helper: string;
  id: string;
  label: string;
  tone: SetupFlowTone;
  value: string;
};

export type SetupFlowView = {
  copy: string;
  metrics: SetupFlowMetric[];
  pill: string;
  title: string;
  tone: SetupFlowTone;
};

function runnerLabel(status: SetupReadiness["runnerStatus"]): string {
  if (status === "ready") return "Online";
  if (status === "registered_offline") return "Registered";
  return "Missing";
}

function verifierLabel(status: SetupReadiness["verifierStatus"]): string {
  if (status === "ready") return "Healthy";
  if (status === "not_tested") return "Not tested";
  if (status === "failing") return "Failing";
  return "Missing";
}

function stateCopy(state: SetupState, agentName: string): Pick<SetupFlowView, "copy" | "pill" | "title" | "tone"> {
  if (state === "live") {
    return {
      copy: "A real protected action produced a matched signed receipt. This agent is live through the verified-action loop.",
      pill: "Live",
      title: `${agentName} is live and verified`,
      tone: "success",
    };
  }
  if (state === "verifier_ready") {
    return {
      copy: "Policy, runner, and verifier are ready. Route one real protected action and wait for the first matched receipt.",
      pill: "Ready for first receipt",
      title: "Run the first protected action",
      tone: "warning",
    };
  }
  if (state === "runner_ready") {
    return {
      copy: "The protected runner is online. Finish verifier health before trusting live action receipts.",
      pill: "Verifier needed",
      title: "Verifier health is the next gate",
      tone: "warning",
    };
  }
  if (state === "runner_registered") {
    return {
      copy: "The runtime policy is enforced and a runner is registered, but execution is not online yet.",
      pill: "Runner pending",
      title: "Bring the runner online",
      tone: "warning",
    };
  }
  if (state === "policy_enforced") {
    return {
      copy: "The runtime policy is enforced. Runner and verifier readiness now decide whether the first action can run.",
      pill: "Policy enforced",
      title: "Control policy is active",
      tone: "warning",
    };
  }
  if (state === "essentials_ready") {
    return {
      copy: "Essentials are complete. Enable the real runtime policy to make this control path enforceable.",
      pill: "Ready to enforce",
      title: "Enable protection for this agent",
      tone: "setup",
    };
  }
  return {
    copy: "Name the agent, choose its first risky action, set thresholds, bind a runner and verifier, then produce the first receipt.",
    pill: "Draft",
    title: "Plan control for the first protected action",
    tone: "setup",
  };
}

export function buildSetupFlowView(readiness: SetupReadiness, agentName: string): SetupFlowView {
  const base = stateCopy(readiness.state, agentName || "Agent");
  return {
    ...base,
    metrics: [
      {
        helper: readiness.essentialComplete ? "Identity, action, thresholds, credential alias, and verifier intent are set." : "Complete the essential fields before enforcement.",
        id: "essentials",
        label: "Essentials",
        tone: readiness.essentialComplete ? "success" : "warning",
        value: readiness.essentialComplete ? "Ready" : "Pending",
      },
      {
        helper: readiness.state === "draft" || readiness.state === "essentials_ready" ? "Runtime policy has not been enforced yet." : "Real runtime gate is active for this project.",
        id: "policy",
        label: "Policy",
        tone: readiness.state === "draft" || readiness.state === "essentials_ready" ? "neutral" : "success",
        value: readiness.state === "draft" || readiness.state === "essentials_ready" ? "Not enforced" : "Enforced",
      },
      {
        helper: readiness.runnerStatus === "ready" ? "Runner can claim authorized attempts." : "Runner must be registered and online for execution.",
        id: "runner",
        label: "Runner",
        tone: readiness.runnerStatus === "ready" ? "success" : readiness.runnerStatus === "registered_offline" ? "warning" : "neutral",
        value: runnerLabel(readiness.runnerStatus),
      },
      {
        helper: readiness.verifierStatus === "ready" ? "Source-of-record test matched." : "Connector must be configured and test-matched.",
        id: "verifier",
        label: "Verifier",
        tone: readiness.verifierStatus === "ready" ? "success" : readiness.verifierStatus === "failing" ? "danger" : "warning",
        value: verifierLabel(readiness.verifierStatus),
      },
      {
        helper: readiness.state === "live" ? "Matched signed receipt exists for this agent." : "Never mark live until a real matched receipt exists.",
        id: "receipt",
        label: "First receipt",
        tone: readiness.state === "live" ? "success" : "warning",
        value: readiness.state === "live" ? "Matched" : "Waiting",
      },
    ],
  };
}
