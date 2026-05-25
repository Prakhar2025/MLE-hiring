"""
schemas.py — Pydantic output model for all 14 required CSV columns.
All fields have defaults so a fallback row can always be generated (prevents crashes).
"""

from typing import List, Any
from pydantic import BaseModel, Field, field_validator
import json

from config import (
    VALID_STATUS, VALID_REQUEST_TYPE, VALID_RISK_LEVEL,
    LOW_CONFIDENCE_FLOOR
)


class TicketOutput(BaseModel):
    """
    One output row — mirrors the output.csv header exactly.
    Field order matches the CSV column order.
    """

    # --- Input pass-through (echo back for CSV alignment) ---
    issue:   str = Field(default="")
    subject: str = Field(default="")
    company: str = Field(default="")

    # --- Primary output fields ---
    response:     str = Field(default="")
    product_area: str = Field(default="general")
    status:       str = Field(default="escalated")
    request_type: str = Field(default="invalid")
    justification: str = Field(default="")

    # --- Extended output fields ---
    confidence_score: float = Field(default=LOW_CONFIDENCE_FLOOR)
    source_documents: str   = Field(default="")   # pipe-separated paths
    risk_level:       str   = Field(default="low")
    pii_detected:     bool  = Field(default=False)
    language:         str   = Field(default="en")
    actions_taken:    str   = Field(default="[]")  # JSON string

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_STATUS:
            return "escalated"
        return v

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_REQUEST_TYPE:
            return "invalid"
        return v

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_RISK_LEVEL:
            return "low"
        return v

    @field_validator("confidence_score")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("actions_taken")
    @classmethod
    def validate_actions_json(cls, v: Any) -> str:
        """Ensure actions_taken is always a valid JSON array string."""
        if isinstance(v, list):
            return json.dumps(v)
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return json.dumps(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
        return "[]"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def to_csv_row(self) -> dict:
        """Returns an ordered dict matching the output.csv column order."""
        return {
            "issue":            self.issue,
            "subject":          self.subject,
            "company":          self.company,
            "response":         self.response,
            "product_area":     self.product_area,
            "status":           self.status,
            "request_type":     self.request_type,
            "justification":    self.justification,
            "confidence_score": round(self.confidence_score, 4),
            "source_documents": self.source_documents,
            "risk_level":       self.risk_level,
            "pii_detected":     str(self.pii_detected).lower(),
            "language":         self.language,
            "actions_taken":    self.actions_taken,
        }


# CSV column order — must match output.csv header exactly
CSV_COLUMNS = [
    "issue", "subject", "company",
    "response", "product_area", "status", "request_type", "justification",
    "confidence_score", "source_documents", "risk_level",
    "pii_detected", "language", "actions_taken",
]


def safe_fallback_row(issue: str, subject: str, company: str, error: str) -> TicketOutput:
    """
    Returns a minimal safe output row used when the agent crashes on a ticket.
    Ensures we never fail to write a row — crashes are penalized -20% across ALL dimensions.
    """
    return TicketOutput(
        issue=issue,
        subject=subject,
        company=company,
        response="Unable to process this request. Please contact support directly.",
        product_area="general",
        status="escalated",
        request_type="invalid",
        justification=f"Agent encountered an internal error: {error[:200]}",
        confidence_score=0.0,
        source_documents="",
        risk_level="low",
        pii_detected=False,
        language="en",
        actions_taken="[]",
    )
