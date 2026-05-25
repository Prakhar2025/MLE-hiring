"""
retriever.py — BM25-based corpus retrieval with source path validation.

Builds an in-memory BM25 index over all 791 markdown files in data/.
Query returns (score, relative_path) pairs — paths are validated to exist.

Usage:
    r = Retriever()
    results = r.query("how do I reset my password", top_k=5, domain="DevPlatform")
    # results: list of (score, "data/devplatform/account/reset-password.md")
"""

import os
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from config import DATA_DIR, REPO_ROOT, BM25_TOP_K, DOMAIN_DIRS


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer. Lowercase."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9']+", text)
    return tokens or [""]


class Retriever:
    """
    Singleton-style corpus index — build once, query many times.
    """

    def __init__(self):
        self._docs: list[str]  = []   # raw text of each doc
        self._paths: list[str] = []   # relative path from REPO_ROOT
        self._domains: list[str] = [] # "DevPlatform" | "Claude" | "Visa" | "api_specs"
        self._bm25: Optional[BM25Okapi] = None
        self._build_index()

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Walk all markdown files in data/ and build BM25 index."""
        print("[Retriever] Building BM25 index over corpus...", flush=True)
        for domain_name, domain_dir in DOMAIN_DIRS.items():
            if not domain_dir.exists():
                continue
            for filepath in sorted(domain_dir.rglob("*.md")):
                try:
                    text = filepath.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                rel_path = filepath.relative_to(REPO_ROOT).as_posix()
                self._docs.append(text)
                self._paths.append(rel_path)
                self._domains.append(domain_name)

        if not self._docs:
            raise RuntimeError("No corpus documents found — check DATA_DIR path.")

        tokenized = [_tokenize(doc) for doc in self._docs]
        self._bm25 = BM25Okapi(tokenized)
        print(f"[Retriever] Index built: {len(self._docs)} documents.", flush=True)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        top_k: int = BM25_TOP_K,
        domain: Optional[str] = None,
    ) -> list[tuple[float, str, str]]:
        """
        Returns list of (score, relative_path, snippet) sorted by score desc.

        Args:
            query_text: the ticket content to search for
            top_k:      max number of results to return
            domain:     if provided, restrict to docs from this domain only
        """
        if not query_text or not query_text.strip():
            return []

        tokens = _tokenize(query_text)
        scores = self._bm25.get_scores(tokens)

        # Pair scores with indices
        indexed = list(enumerate(scores))

        # Filter by domain if specified
        if domain and domain in DOMAIN_DIRS:
            indexed = [(i, s) for i, s in indexed if self._domains[i] == domain]

        # Sort by score descending
        indexed.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed[:top_k]:
            if score <= 0.0:
                continue
            path = self._paths[idx]
            # Validate file exists on disk
            full_path = REPO_ROOT / path
            if not full_path.exists():
                continue
            snippet = self._get_snippet(self._docs[idx], query_text)
            results.append((float(score), path, snippet))

        return results

    def query_multi_domain(
        self,
        query_text: str,
        top_k: int = BM25_TOP_K,
    ) -> list[tuple[float, str, str]]:
        """Query across all domains, return top_k globally."""
        return self.query(query_text, top_k=top_k, domain=None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_snippet(self, doc_text: str, query: str, max_chars: int = 400) -> str:
        """Extract the most relevant snippet from a document."""
        # Find the sentence/paragraph containing query terms
        query_words = set(_tokenize(query))
        paragraphs = [p.strip() for p in doc_text.split("\n\n") if p.strip()]

        best_para = ""
        best_overlap = 0
        for para in paragraphs:
            para_words = set(_tokenize(para))
            overlap = len(query_words & para_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_para = para

        snippet = best_para[:max_chars] if best_para else doc_text[:max_chars]
        return snippet.replace("\n", " ").strip()

    def validate_paths(self, pipe_separated: str) -> str:
        """
        Takes a pipe-separated source_documents string, validates each path
        actually exists in the repo, and returns only valid ones.
        This prevents hallucinated citations.
        """
        if not pipe_separated or not pipe_separated.strip():
            return ""
        paths = [p.strip() for p in pipe_separated.split("|") if p.strip()]
        valid = []
        for p in paths:
            full = REPO_ROOT / p
            if full.exists():
                valid.append(p)
        return "|".join(valid)

    def paths_to_context(self, paths_str: str, max_chars_per_doc: int = 800) -> str:
        """
        Given a pipe-separated path string, return concatenated document
        excerpts to feed into the LLM as context.
        """
        if not paths_str:
            return ""
        snippets = []
        for p in paths_str.split("|"):
            p = p.strip()
            if not p:
                continue
            full = REPO_ROOT / p
            if full.exists():
                try:
                    content = full.read_text(encoding="utf-8", errors="ignore")
                    snippets.append(f"=== {p} ===\n{content[:max_chars_per_doc]}")
                except OSError:
                    pass
        return "\n\n".join(snippets)
