"""Controlled evidence-to-language commentary."""

from .providers import (
    CommentaryEvidence,
    CommentaryProvider,
    DeterministicTemplateProvider,
    MockCommentaryProvider,
    verify_numerical_claims,
)

__all__ = [
    "CommentaryEvidence",
    "CommentaryProvider",
    "DeterministicTemplateProvider",
    "MockCommentaryProvider",
    "verify_numerical_claims",
]
