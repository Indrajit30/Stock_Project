import re

SYSTEM_PROMPT_BASE = (
    "You are a financial research analyst. You ONLY use information from the provided "
    "documents. Every numerical claim must be cited with [Source: document_name]. "
    "If data is not in the provided documents, write 'Data not available' — never "
    "guess or use prior knowledge for financial figures. You are honest and precise."
)

_CITE_BRACKET = re.compile(r'\[Source:\s*([^\]]+)\]', re.IGNORECASE)
_CITE_TAG = re.compile(r'<cite>(.*?)</cite>', re.IGNORECASE | re.DOTALL)
_NUMBER_RE = re.compile(r'\d')


class CitationGuard:
    def extract_citations(self, text: str) -> list[dict]:
        results = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for sentence in sentences:
            sources = _CITE_BRACKET.findall(sentence) + _CITE_TAG.findall(sentence)
            for source in sources:
                results.append({
                    "claim": sentence.strip(),
                    "source": source.strip(),
                    "source_url": None,
                })
        return results

    def validate_citations(self, claims: list[dict], allowed_sources: list[str]) -> list[dict]:
        allowed_lower = [s.lower() for s in allowed_sources]
        for claim in claims:
            source_lower = claim.get("source", "").lower()
            claim["verification_status"] = (
                "VERIFIED"
                if any(a in source_lower or source_lower in a for a in allowed_lower)
                else "UNVERIFIED"
            )
        return claims

    def strip_unverified_claims(self, text: str, verified_sources: list[str]) -> str:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        out = []
        for sentence in sentences:
            has_number = bool(_NUMBER_RE.search(sentence))
            has_citation = bool(_CITE_BRACKET.search(sentence) or _CITE_TAG.search(sentence))
            if has_number and not has_citation:
                out.append("[Data not available from verified sources]")
            else:
                out.append(sentence)
        return " ".join(out)

    def build_citation_prompt(self, data_context: str, allowed_sources: list[str]) -> str:
        sources_list = "\n".join(f"  - {s}" for s in allowed_sources)
        return (
            f"You have access to the following verified data sources:\n{sources_list}\n\n"
            f"Rules:\n"
            f"1. Cite every numerical claim with [Source: exact_source_name]\n"
            f"2. Write 'Data not available' if the answer is not in the provided context\n"
            f"3. Never use information not present in the provided documents\n"
            f"4. List all sources used at the end of your response\n\n"
            f"Data context:\n{data_context}"
        )


citation_guard = CitationGuard()
