from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.detectors._payload import _as_float, _as_str, _pick


_RAG_GROUNDING_CONFIDENCE = 0.89


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _retrieval_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for key in ("retrieval", "rag", "retrieval_context"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            records.append(value)
    for key in ("rag_docs", "retrieved_documents", "documents", "sources"):
        docs = _as_list(payload.get(key))
        if docs:
            records.append({"documents": docs})
    trace = _as_mapping(payload.get("trace_graph"))
    for span in _as_list(trace.get("spans")):
        if not isinstance(span, Mapping):
            continue
        retrieval = _as_mapping(span.get("retrieval"))
        if retrieval or _as_str(span.get("span_type")).lower() in {"rag", "retrieval"}:
            records.append(retrieval or span)
    return records


def detect(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    return detect_rag_grounding_failure(payload)


def detect_rag_grounding_failure(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    final_answer = _as_str(
        _pick(payload, ("final_answer",), ("output_text",), ("response", "content"), ("output",))
    )
    judge_groundedness = _as_float(
        _pick(
            payload,
            ("judge", "groundedness"),
            ("judge", "groundedness_score"),
            ("groundedness_score",),
        ),
        fallback=-1.0,
    )
    if judge_groundedness >= 0 and judge_groundedness < 0.45:
        return _result(
            reason=f"groundedness score was {judge_groundedness:.2f}",
            trigger_rule="low_groundedness_score",
            evidence={"groundedness_score": judge_groundedness},
        )

    retrievals = _retrieval_records(payload)
    if not retrievals:
        rag_expected = bool(
            _as_str(
                _pick(
                    payload,
                    ("required_document",),
                    ("contract", "required_document"),
                    ("rag_required",),
                    ("retrieval_required",),
                    ("grounding_required",),
                )
            )
        )
        if final_answer and rag_expected:
            return _result(
                reason="answer was produced without captured retrieval evidence",
                trigger_rule="answer_without_retrieval_evidence",
                evidence={"has_final_answer": True},
            )
        return None

    for retrieval in retrievals:
        docs = (
            _as_list(retrieval.get("documents"))
            or _as_list(retrieval.get("docs"))
            or _as_list(retrieval.get("chunks"))
            or _as_list(retrieval.get("sources"))
        )
        required_doc = _as_str(
            retrieval.get("required_document")
            or retrieval.get("required_doc")
            or _pick(payload, ("required_document",), ("contract", "required_document"))
        )
        top_score = _as_float(
            retrieval.get("top_score")
            or retrieval.get("max_score")
            or retrieval.get("similarity")
            or retrieval.get("score"),
            fallback=-1.0,
        )
        if required_doc and docs and not _docs_contain(docs, required_doc):
            return _result(
                reason=f"required document {required_doc} was not retrieved",
                trigger_rule="required_document_missing",
                evidence={"required_document": required_doc, "document_count": len(docs)},
            )
        if docs == [] and final_answer:
            return _result(
                reason="retrieval returned no documents before the final answer",
                trigger_rule="empty_retrieval_with_answer",
                evidence={"document_count": 0},
            )
        if top_score >= 0 and top_score < 0.35 and final_answer:
            return _result(
                reason=f"top retrieval score was weak ({top_score:.2f})",
                trigger_rule="weak_retrieval_score",
                evidence={"top_score": top_score, "document_count": len(docs)},
            )
    return None


def _docs_contain(docs: list[Any], required_doc: str) -> bool:
    needle = required_doc.lower()
    for doc in docs:
        if isinstance(doc, Mapping):
            text = " ".join(
                str(doc.get(key) or "")
                for key in ("id", "title", "name", "source", "document_type")
            ).lower()
        else:
            text = str(doc).lower()
        if needle in text:
            return True
    return False


def _result(*, reason: str, trigger_rule: str, evidence: dict[str, Any]) -> dict[str, Any]:
    signature = f"rag_grounding_failure:{trigger_rule}:{reason[:120]}"
    return {
        "category": "RAG_GROUNDING_FAILURE",
        "speed_class": "pattern",
        "confidence": _RAG_GROUNDING_CONFIDENCE,
        "what_happened": "The answer was not sufficiently grounded in retrieved evidence.",
        "why_it_matters": "RAG agents can sound confident while using stale, missing, or weak context.",
        "root_cause": reason,
        "recommended_next_action": "Replay the trace with frozen retrieval and assert required sources before promoting the fix.",
        "grouping_signature": signature,
        "severity_hint": "high",
        "evidence": {
            **evidence,
            "trigger_rule": trigger_rule,
        },
    }
