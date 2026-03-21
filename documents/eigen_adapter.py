"""Thin Eigen document adapter for extracting structured supporting evidence."""

from __future__ import annotations

import re
from uuid import uuid4

from contracts.models import DocumentExtractionResult, WorkflowSchema
from validation.validators import parse_numeric


class EigenDocumentAdapter:
    """Heuristic adapter that normalizes extracted document fields."""

    def extract_fields(self, workflow: WorkflowSchema, document_text: str) -> DocumentExtractionResult:
        extracted_fields: dict[str, str] = {}
        confidence: dict[str, float] = {}

        for field in workflow.required_fields + workflow.optional_fields:
            if not field.document_extractable:
                continue
            value = self._extract_value(field.name, document_text)
            if value is None:
                continue
            extracted_fields[field.name] = value
            confidence[field.name] = 0.96 if field.name in {"charge_amount", "charge_date"} else 0.8

        status = "completed" if extracted_fields else "needs_review"
        return DocumentExtractionResult(
            job_id=f"eigen-{uuid4().hex[:10]}",
            status=status,
            fields=extracted_fields,
            confidence=confidence,
        )

    def _extract_value(self, field_name: str, document_text: str) -> str | None:
        if field_name == "charge_amount":
            match = re.search(
                r"(?:amount|charge amount)\s*[:\-]\s*(\$?\d+(?:,\d{3})*(?:\.\d{2})?)",
                document_text,
                re.IGNORECASE,
            )
            if match:
                numeric = parse_numeric(match.group(1))
                if numeric is not None:
                    return f"${numeric:.2f}"
            match = re.search(r"\$\d+(?:,\d{3})*(?:\.\d{2})?", document_text)
            if match:
                numeric = parse_numeric(match.group(0))
                if numeric is not None:
                    return f"${numeric:.2f}"
        if field_name == "charge_date":
            match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", document_text)
            if match:
                return match.group(0)
            match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", document_text)
            if match:
                return match.group(0)
        if field_name == "merchant_name":
            match = re.search(r"(?:merchant|vendor)\s*[:\-]\s*([A-Za-z0-9 &.-]+)", document_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        if field_name == "reference_number":
            match = re.search(r"(?:reference|ref)\s*[:#\-]?\s*([A-Z0-9\-]{4,20})", document_text, re.IGNORECASE)
            if match:
                return match.group(1).strip().upper()
        return None
