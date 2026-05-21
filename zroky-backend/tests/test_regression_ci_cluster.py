"""Tests for `app.services.regression_ci.cluster`.

Coverage:
  - Greedy clustering: traces with similar embeddings merge; dissimilar
    traces form separate clusters.
  - Embedder failure: traces with no embedding land in a fallback bucket.
  - No embedder: single unclustered bucket using TF-IDF labels.
  - Top-N capping + singleton filtering.
  - TF-IDF labels: rare discriminative terms outrank common terms.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.regression_ci.cluster import (
    MERGE_THRESHOLD,
    RegressedTrace,
    _label_tokens,
    _top_keywords,
    cluster_regressions,
)


# ── stubs ───────────────────────────────────────────────────────────────────


@dataclass
class _StubEmbedder:
    """Returns hand-picked vectors per input. Deterministic. None signals
    a failure for that input."""

    text_to_vec: dict[str, list[float] | None]
    raise_on: set[str] | None = None

    def generate_embedding(self, text: str) -> list[float] | None:
        if self.raise_on and text in self.raise_on:
            raise RuntimeError(f"simulated failure on {text!r}")
        return self.text_to_vec.get(text)


# ── label / TF-IDF helpers ─────────────────────────────────────────────────


class TestLabelTokens:
    def test_drops_stopwords(self) -> None:
        toks = _label_tokens("the refund policy for the customer")
        assert "the" not in toks
        assert "for" not in toks
        assert "refund" in toks
        assert "policy" in toks
        assert "customer" in toks

    def test_lowercases_and_drops_short(self) -> None:
        toks = _label_tokens("A B Refund POLICY")
        assert "refund" in toks
        assert "policy" in toks
        assert "a" not in toks  # length < 2
        assert "b" not in toks


class TestTopKeywords:
    def test_empty_corpus(self) -> None:
        assert _top_keywords([], k=3) == []

    def test_rare_terms_win_over_common(self) -> None:
        # "refund" appears in every doc (common, low IDF), "german" only once
        # (rare, high IDF). German should outrank refund.
        corpus = [
            "refund policy english",
            "refund policy french",
            "refund policy german obscure_term",
        ]
        top = _top_keywords(corpus, k=3)
        # refund appears 3x in tf but its idf is 0 (in every doc)
        # german + obscure_term each appear once, idf = log(3/1) > 0
        assert "german" in top or "obscure_term" in top
        assert "refund" not in top  # idf=0 kills it

    def test_single_doc_falls_back_to_frequency(self) -> None:
        top = _top_keywords(["refund policy refund customer"], k=2)
        # With n=1, IDF=1.0 → ranked by raw frequency.
        # "refund" appears twice, "policy"/"customer" once each.
        assert top[0] == "refund"


# ── clustering ──────────────────────────────────────────────────────────────


class TestClusterRegressions:
    def test_empty_returns_empty(self) -> None:
        assert cluster_regressions([]) == ()

    def test_no_embedder_returns_single_bucket(self) -> None:
        traces = [
            RegressedTrace(trace_id=f"t{i}", input_text=f"refund policy question {i}")
            for i in range(5)
        ]
        clusters = cluster_regressions(traces, embedder=None)
        assert len(clusters) == 1
        assert clusters[0].size == 5

    def test_similar_inputs_merge(self) -> None:
        # 3 traces, vectors nearly identical → should form ONE cluster.
        traces = [
            RegressedTrace(trace_id="t1", input_text="refund policy DE 1"),
            RegressedTrace(trace_id="t2", input_text="refund policy DE 2"),
            RegressedTrace(trace_id="t3", input_text="refund policy DE 3"),
        ]
        emb = _StubEmbedder(text_to_vec={
            "refund policy DE 1": [1.0, 0.0, 0.0],
            "refund policy DE 2": [0.99, 0.05, 0.0],
            "refund policy DE 3": [0.98, 0.10, 0.0],
        })
        clusters = cluster_regressions(traces, embedder=emb, min_size=1)
        assert len(clusters) == 1
        assert clusters[0].size == 3

    def test_dissimilar_inputs_split(self) -> None:
        # 4 traces, 2 in each of 2 orthogonal directions → 2 clusters.
        traces = [
            RegressedTrace(trace_id="t1", input_text="alpha branch refund"),
            RegressedTrace(trace_id="t2", input_text="alpha branch policy"),
            RegressedTrace(trace_id="t3", input_text="beta domain shipping"),
            RegressedTrace(trace_id="t4", input_text="beta domain delivery"),
        ]
        emb = _StubEmbedder(text_to_vec={
            "alpha branch refund": [1.0, 0.0],
            "alpha branch policy": [0.99, 0.01],
            "beta domain shipping": [0.0, 1.0],
            "beta domain delivery": [0.01, 0.99],
        })
        clusters = cluster_regressions(traces, embedder=emb, min_size=1)
        assert len(clusters) == 2
        sizes = sorted(c.size for c in clusters)
        assert sizes == [2, 2]

    def test_embedder_failure_falls_back_to_unclustered(self) -> None:
        traces = [
            RegressedTrace(trace_id="t1", input_text="a b c"),
            RegressedTrace(trace_id="t2", input_text="d e f"),
        ]
        emb = _StubEmbedder(text_to_vec={"a b c": None, "d e f": None})
        clusters = cluster_regressions(traces, embedder=emb, min_size=1)
        # All embedding failed → single unclustered bucket.
        assert len(clusters) == 1
        assert clusters[0].size == 2

    def test_singleton_filter(self) -> None:
        # Two clusters of sizes [3, 1] with min_size=2 → only the size-3 survives.
        traces = [
            RegressedTrace(trace_id="t1", input_text="alpha 1"),
            RegressedTrace(trace_id="t2", input_text="alpha 2"),
            RegressedTrace(trace_id="t3", input_text="alpha 3"),
            RegressedTrace(trace_id="t4", input_text="orthogonal beta"),
        ]
        emb = _StubEmbedder(text_to_vec={
            "alpha 1": [1.0, 0.0],
            "alpha 2": [0.98, 0.02],
            "alpha 3": [0.97, 0.03],
            "orthogonal beta": [0.0, 1.0],
        })
        clusters = cluster_regressions(traces, embedder=emb, min_size=2)
        assert len(clusters) == 1
        assert clusters[0].size == 3

    def test_top_n_cap(self) -> None:
        # Build 7 distinct orthogonal-ish clusters; cap at 3.
        traces: list[RegressedTrace] = []
        vec_map: dict[str, list[float] | None] = {}
        for i in range(7):
            # Each trace gets a "two-hot" vector at a unique pair of indices.
            vec = [0.0] * 7
            vec[i] = 1.0
            # Give two traces per cluster to survive min_size=2.
            for j in (0, 1):
                txt = f"topic{i} variant{j}"
                # Same vector for both variants (will merge).
                traces.append(RegressedTrace(trace_id=f"t{i}{j}", input_text=txt))
                vec_map[txt] = list(vec)
        emb = _StubEmbedder(text_to_vec=vec_map)
        clusters = cluster_regressions(traces, embedder=emb, top_n=3, min_size=2)
        assert len(clusters) == 3

    def test_sorted_by_size_desc(self) -> None:
        # Cluster A: 3 traces, Cluster B: 2 traces. A must come first.
        traces = [
            RegressedTrace(trace_id="a1", input_text="alpha 1"),
            RegressedTrace(trace_id="a2", input_text="alpha 2"),
            RegressedTrace(trace_id="a3", input_text="alpha 3"),
            RegressedTrace(trace_id="b1", input_text="orthogonal x"),
            RegressedTrace(trace_id="b2", input_text="orthogonal y"),
        ]
        emb = _StubEmbedder(text_to_vec={
            "alpha 1": [1.0, 0.0],
            "alpha 2": [0.99, 0.01],
            "alpha 3": [0.97, 0.03],
            "orthogonal x": [0.0, 1.0],
            "orthogonal y": [0.02, 0.98],
        })
        clusters = cluster_regressions(traces, embedder=emb, min_size=1)
        assert clusters[0].size >= clusters[-1].size

    def test_sample_input_truncated(self) -> None:
        long_input = "x" * 500
        traces = [
            RegressedTrace(trace_id="t1", input_text=long_input),
            RegressedTrace(trace_id="t2", input_text=long_input),
        ]
        emb = _StubEmbedder(text_to_vec={long_input: [1.0, 0.0]})
        clusters = cluster_regressions(traces, embedder=emb, min_size=1)
        assert len(clusters[0].sample_input) <= 280  # SAMPLE_INPUT_MAX_CHARS

    def test_threshold_too_high_creates_singletons(self) -> None:
        # With threshold=0.95 vectors must be near-identical to merge.
        # [1.0, 0.0] vs [0.7, 0.3] -> cosine ~= 0.919 -> below 0.95 -> split.
        traces = [
            RegressedTrace(trace_id="t1", input_text="hello world a"),
            RegressedTrace(trace_id="t2", input_text="hello world b"),
        ]
        emb = _StubEmbedder(text_to_vec={
            "hello world a": [1.0, 0.0],
            "hello world b": [0.7, 0.3],
        })
        clusters = cluster_regressions(
            traces, embedder=emb, merge_threshold=0.95, min_size=1,
        )
        assert len(clusters) == 2
