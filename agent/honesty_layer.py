import json
import re

from pydantic import BaseModel

FINANCIAL_PATTERN = re.compile(
    r'\$[\d,]+|\d+\.?\d*%|\d+\.?\d*x|\d+\.?\d*B|\d+\.?\d*M'
)
_CITATION_RE = re.compile(r'\[Source:[^\]]+\]', re.IGNORECASE)
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


class AuditResult(BaseModel):
    passed: bool
    flagged_claims: list[str]
    confidence_penalty: float


class HonestyLayer:
    def audit_response(self, response_text: str, source_data: dict) -> AuditResult:
        claimed_numbers = FINANCIAL_PATTERN.findall(response_text)
        source_text = json.dumps(source_data, default=str).lower()

        flagged = []
        for number in claimed_numbers:
            normalized = (
                number.replace("$", "")
                      .replace(",", "")
                      .replace("%", "")
                      .replace("x", "")
                      .replace("B", "")
                      .replace("M", "")
                      .lower()
            )
            if normalized and normalized not in source_text:
                flagged.append(number)

        return AuditResult(
            passed=len(flagged) == 0,
            flagged_claims=flagged,
            confidence_penalty=min(len(flagged) * 0.1, 1.0),
        )

    def sanitize_response(self, response_text: str, audit: AuditResult) -> str:
        if audit.passed:
            return response_text

        sanitized = response_text
        for claim in audit.flagged_claims:
            sanitized = sanitized.replace(claim, "[unverified figure removed]")

        sanitized += f"\n\nNote: {len(audit.flagged_claims)} unverified figures were removed."
        return sanitized

    def enforce_data_not_found(self, response_text: str) -> str:
        sentences = _SENTENCE_RE.split(response_text)
        out = []
        for sentence in sentences:
            has_number = bool(FINANCIAL_PATTERN.search(sentence))
            has_citation = bool(_CITATION_RE.search(sentence))
            if has_number and not has_citation:
                out.append("[Data not available — source not in verified documents]")
            else:
                out.append(sentence)
        return " ".join(out)


honesty_layer = HonestyLayer()
