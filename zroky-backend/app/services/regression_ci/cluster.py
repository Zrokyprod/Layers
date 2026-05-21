"""
Regression clustering for the PR-comment "where are the regressions" section.

Algorithm: **greedy cosine clustering** — single-pass, deterministic,
zero new dependencies. Chosen over HDBSCAN/KMeans because:

  - HDBSCAN adds a heavy native dependency for marginal gain at our scale
    (we cluster ~10-500 regressed inputs per run, not 1M).
  - KMeans requires a pre-chosen K; we don't know K up front.
  - Greedy single-pass with a cosine threshold is O(N*K) where K is the
    final cluster count (typically <50). Bounded, predictable, easy to
    debug, no model files to ship.

Procedure (per regressed trace):
  1. Embed the trace's input text.
  2. Find nearest existing cluster by cosine to centroid.
  3. If cosine >= MERGE_THRESHOLD, add to that cluster and update centroid.
  4. Otherwise, start a new cluster.

Labels: top-3 TF-IDF terms across cluster member inputs (corpus = all
regressed inputs). Pure-Python — uses `collections.Counter`.

The clusterer is **fail-soft**: if the embedder errors on every input,
we still return one big UNCLUSTERED cluster so the PR comment has
something to display.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, Sequence

from app.services.regression_ci.models import RegressionCluster

logger = logging.getLogger(__name__)


# ── tunables ────────────────────────────────────────────────────────────────

# Cosine threshold for merging into an existing cluster. Higher = more
# clusters (over-segmented). Lower = fewer clusters (under-segmented).
# 0.80 chosen by inspection on natural-language inputs — keeps semantic
# variants together while separating distinct topics.
MERGE_THRESHOLD: float = 0.80

# Top-N clusters returned. PR comments get noisy past 5 even when more
# real clusters exist.
TOP_N: int = 5

# Cluster must have at least this many traces to be reported. Singletons
# are usually noise and not actionable for a PR reviewer.
MIN_CLUSTER_SIZE: int = 2

# Truncation for sample_input shown in the PR comment.
SAMPLE_INPUT_MAX_CHARS: int = 280


# ── input types ─────────────────────────────────────────────────────────────


class Embedder(Protocol):
    def generate_embedding(self, text: str) -> list[float] | None: ...


@dataclass(frozen=True)
class RegressedTrace:
    """Minimal info needed to cluster a regressed trace.

    The orchestrator builds these from `TraceResult` rows where
    diff_score.verdict == FAIL.
    """

    trace_id: str
    input_text: str

    def short_input(self, n: int = SAMPLE_INPUT_MAX_CHARS) -> str:
        if len(self.input_text) <= n:
            return self.input_text
        return self.input_text[: n - 3] + "..."


# ── tokenization for TF-IDF labels ──────────────────────────────────────────

# Same shape as diff_metric.tokenize but with stopword filtering — useful
# for label terms (we don't want "the" as the top cluster keyword).
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}")

_STOPWORDS: frozenset[str] = frozenset({
    # Top function words / determiners — empirically the noisiest cluster
    # labels. Kept short to avoid over-filtering domain terms.
    "the", "and", "for", "with", "from", "this", "that", "what", "which",
    "have", "has", "had", "are", "was", "were", "you", "your", "our",
    "their", "them", "they", "his", "her", "its", "ours", "out", "into",
    "but", "not", "can", "will", "would", "could", "should", "may",
    "more", "most", "less", "only", "some", "any", "all",
})


def _label_tokens(text: str) -> list[str]:
    return [
        tok.lower() for tok in _TOKEN_RE.findall(text or "")
        if tok.lower() not in _STOPWORDS
    ]


# ── internal cluster state ──────────────────────────────────────────────────


@dataclass
class _Cluster:
    """Mutable cluster used during the single-pass build.

    Becomes a frozen RegressionCluster at the end via `_finalize`.
    """

    centroid: list[float]
    members: list[RegressedTrace] = field(default_factory=list)

    def update_centroid(self, new_vec: list[float]) -> None:
        """Online mean — keeps the centroid as the average of all members.

        For unit-length input vectors, this is the standard centroid; for
        non-unit vectors, this still works well for cosine because cosine
        is scale-invariant.
        """
        n = len(self.members)  # already includes the new member when called
        if n == 0:
            self.centroid = list(new_vec)
            return
        # Streaming mean: c_new = c_old + (x - c_old) / n
        for i in range(min(len(self.centroid), len(new_vec))):
            self.centroid[i] = self.centroid[i] + (new_vec[i] - self.centroid[i]) / n


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    raw = dot / (math.sqrt(na) * math.sqrt(nb))
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


# ── public API ──────────────────────────────────────────────────────────────


def cluster_regressions(
    regressed: Sequence[RegressedTrace],
    *,
    embedder: Embedder | None = None,
    merge_threshold: float = MERGE_THRESHOLD,
    top_n: int = TOP_N,
    min_size: int = MIN_CLUSTER_SIZE,
) -> tuple[RegressionCluster, ...]:
    """Cluster regressed traces by semantic similarity of their inputs.

    Returns up to `top_n` clusters sorted by descending size. Clusters
    smaller than `min_size` are dropped unless that would result in
    returning zero clusters AND there are regressed traces (in which case
    we return a single UNCLUSTERED bucket so the PR comment isn't empty).
    """
    if not regressed:
        return tuple()

    # Fast path: no embedder → single UNCLUSTERED bucket using TF-IDF labels
    # on the raw input text. This keeps the PR comment useful even when
    # embedding API is unavailable.
    if embedder is None:
        return (_unclustered(regressed),)

    clusters: list[_Cluster] = []
    unembedded: list[RegressedTrace] = []

    for trace in regressed:
        try:
            vec = embedder.generate_embedding(trace.input_text)
        except Exception as exc:
            logger.warning("regression_ci.cluster embedder failed: %s", exc)
            vec = None

        if vec is None:
            unembedded.append(trace)
            continue

        if not clusters:
            c = _Cluster(centroid=list(vec))
            c.members.append(trace)
            clusters.append(c)
            continue

        best_i = -1
        best_sim = -1.0
        for i, c in enumerate(clusters):
            sim = _cosine(c.centroid, vec)
            if sim > best_sim:
                best_sim = sim
                best_i = i

        if best_sim >= merge_threshold and best_i >= 0:
            clusters[best_i].members.append(trace)
            clusters[best_i].update_centroid(vec)
        else:
            c = _Cluster(centroid=list(vec))
            c.members.append(trace)
            clusters.append(c)

    # If every trace failed embedding, return a single unclustered bucket.
    if not clusters and unembedded:
        return (_unclustered(unembedded),)

    # Add unembedded traces to a separate "no-embedding" bucket so they
    # still appear in the report. Suppress when empty.
    if unembedded:
        no_emb = _Cluster(centroid=[0.0])
        no_emb.members.extend(unembedded)
        clusters.append(no_emb)

    finalized = [_finalize(c) for c in clusters]
    finalized.sort(key=lambda x: x.size, reverse=True)

    # Drop singletons (likely noise), but keep at least one if we'd
    # otherwise return zero clusters.
    filtered = [c for c in finalized if c.size >= min_size]
    if not filtered and finalized:
        filtered = [finalized[0]]

    return tuple(filtered[:top_n])


# ── internals ───────────────────────────────────────────────────────────────


def _finalize(c: _Cluster) -> RegressionCluster:
    """Convert internal mutable cluster → frozen RegressionCluster."""
    keywords = _top_keywords([m.input_text for m in c.members], k=3)
    label = "_".join(keywords) if keywords else "unlabeled"
    sample = c.members[0]
    return RegressionCluster(
        label=label,
        keywords=tuple(keywords),
        size=len(c.members),
        sample_trace_id=sample.trace_id,
        sample_input=sample.short_input(),
    )


def _unclustered(regressed: Sequence[RegressedTrace]) -> RegressionCluster:
    """Build a single cluster covering all traces when we have no embeddings."""
    keywords = _top_keywords([t.input_text for t in regressed], k=3)
    label = "_".join(keywords) if keywords else "unclustered"
    sample = regressed[0]
    return RegressionCluster(
        label=label,
        keywords=tuple(keywords),
        size=len(regressed),
        sample_trace_id=sample.trace_id,
        sample_input=sample.short_input(),
    )


def _top_keywords(texts: Sequence[str], *, k: int = 3) -> list[str]:
    """Return top-k terms ranked by TF-IDF over the regressed corpus.

    Treats `texts` as the document set. Terms that appear in many
    documents get down-weighted (the typical TF-IDF behavior); rare
    discriminative terms float to the top.
    """
    if not texts:
        return []

    docs = [_label_tokens(t) for t in texts]
    if not any(docs):
        return []

    n_docs = len(docs)
    # Document frequency per term.
    df: Counter[str] = Counter()
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1

    # TF over the merged corpus.
    tf: Counter[str] = Counter()
    for tokens in docs:
        for term in tokens:
            tf[term] += 1

    # TF-IDF score: tf * log(N / df). For N=1, log(1)=0 → fall back to raw TF.
    scored: list[tuple[str, float]] = []
    for term, freq in tf.items():
        if n_docs > 1:
            idf = math.log(n_docs / df[term]) if df[term] > 0 else 0.0
        else:
            idf = 1.0  # single-doc corpus: just rank by frequency
        scored.append((term, freq * idf))

    scored.sort(key=lambda x: (-x[1], x[0]))  # tie-break alphabetical for determinism
    return [t for t, _ in scored[:k]]
