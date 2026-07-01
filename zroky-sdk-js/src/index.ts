// SPDX-License-Identifier: FSL-1.1-MIT
// Copyright 2026 Zroky AI

export { wrap } from "./wrap";
export { trace, traceRun } from "./trace";
export { init } from "./config";
export {
  guard,
  ZrokyRuntimePolicyApprovalRequired,
  ZrokyRuntimePolicyBlocked,
  ZrokyRuntimePolicyError,
} from "./guard";
export {
  awaitActionProof,
  verifiedAction,
  ZrokyVerifiedActionApprovalRequired,
  ZrokyVerifiedActionBlocked,
  ZrokyVerifiedActionError,
} from "./verified-action";
export { verifyOutcome, ZrokyOutcomeVerificationError } from "./verify";
export { outcome } from "./outcome";
export { promptFingerprint } from "./fingerprint";
export { captureHandoff, captureMemory, capturePolicyDecision, captureRetrieval, captureToolCall } from "./spans";
export {
  PHASE1_NATIVE_TOOL_FAMILIES,
  PHASE1_RISKY_ACTION_TYPES,
  PHASE1_RUNTIME_PATHS,
  PHASE1_VERIFICATION_CONNECTORS,
  ZROKY_AGENT_TOOL_CONTROL_SCHEMA_VERSION,
} from "./contracts";
export type { ZrokyConfig, CapturePayload } from "./types";
export type { GuardOptions, RuntimePolicyDecision } from "./guard";
export type {
  ActionProofResult,
  AwaitActionProofOptions,
  VerifiedActionDecision,
  VerifiedActionOptions,
} from "./verified-action";
export type {
  OutcomeReconciliationView,
  OutcomeVerificationVerdict,
  SavedVerificationConnector,
  VerifyCrmRecordOutcomeOptions,
  VerifyGenericRestOutcomeOptions,
  VerifyLedgerRefundOutcomeOptions,
  VerifyOutcomeOptions,
} from "./verify";
export type { OutcomeOptions } from "./outcome";
export type { TraceRunContext, TraceRunOptions } from "./trace";
export type {
  ZrokyAgentProfile,
  ZrokyAuditEvent,
  ZrokyConnectorTemplate,
  ZrokyEvidencePackContract,
  ZrokyJsonValue,
  ZrokyNativeToolFamily,
  ZrokyPolicyDecisionContract,
  ZrokyPolicyDecisionStatus,
  ZrokyRiskActionType,
  ZrokyRuntimePath,
  ZrokyToolActionPassport,
  ZrokyVerificationConnectorType,
  ZrokyVerificationResult,
  ZrokyVerificationVerdict,
} from "./contracts";
export type {
  HandoffCaptureOptions,
  MemoryCaptureOptions,
  PolicyDecisionCaptureOptions,
  RetrievalCaptureOptions,
  RetrievedDocument,
  ToolCaptureOptions,
} from "./spans";
