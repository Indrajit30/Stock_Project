import logging

from shared.schemas import PeerComparisonRow
from agent.llm_router import llm_router
from agent.citation_guard import SYSTEM_PROMPT_BASE

logger = logging.getLogger(__name__)


class PeerAnalyzer:
    async def generate_peer_narrative(
        self, subject: str, peers: list[PeerComparisonRow]
    ) -> str:
        metrics_table = self.format_peer_table(subject, peers)
        prompt = (
            f"Compare {subject} to its sector peers:\n\n"
            f"{metrics_table}\n\n"
            f"Write 3-4 sentences explaining:\n"
            f"1. Where {subject} is most differentiated vs peers "
            f"(premium or discount valuation and why)\n"
            f"2. The most important metric where {subject} leads or lags\n"
            f"3. Any red flags visible only in the peer comparison context\n\n"
            f"Cite every number with [Source: DefeatBeta TTM Metrics].\n"
            f"Be specific with numbers, not vague comparisons."
        )
        return await llm_router.complete_fast(prompt, system=SYSTEM_PROMPT_BASE)

    def format_peer_table(self, subject: str, peers: list[PeerComparisonRow]) -> str:
        header = (
            f"{'':3}{'Ticker':<8} {'PE':>8} {'EV/EBITDA':>10} "
            f"{'Gross Mgn':>10} {'Rev Growth':>11} {'D/E':>6}"
        )
        sep = "-" * len(header)
        lines = [header, sep]

        for row in peers:
            marker = ">>>" if row.ticker.upper() == subject.upper() else "   "
            lines.append(
                f"{marker}{row.ticker:<5} "
                f"{self._fmt(row.pe_ratio):>8} "
                f"{self._fmt(row.ev_ebitda):>10} "
                f"{self._fmt(row.gross_margin, pct=True):>10} "
                f"{self._fmt(row.revenue_growth, pct=True):>11} "
                f"{self._fmt(row.debt_equity):>6}"
            )

        lines.append(sep)

        def avg(field: str):
            vals = [getattr(r, field) for r in peers if getattr(r, field) is not None]
            return sum(vals) / len(vals) if vals else None

        lines.append(
            f"   {'Sector Avg':<8} "
            f"{self._fmt(avg('pe_ratio')):>8} "
            f"{self._fmt(avg('ev_ebitda')):>10} "
            f"{self._fmt(avg('gross_margin'), pct=True):>10} "
            f"{self._fmt(avg('revenue_growth'), pct=True):>11} "
            f"{self._fmt(avg('debt_equity')):>6}"
        )
        return "\n".join(lines)

    def _fmt(self, val, pct: bool = False) -> str:
        if val is None:
            return "N/A"
        return f"{val:.1f}%" if pct else f"{val:.1f}x"

    async def rank_peers_by_attractiveness(
        self, peers: list[PeerComparisonRow]
    ) -> list[dict]:
        scored = []
        for peer in peers:
            pe = peer.pe_ratio or 50.0
            gm = (peer.gross_margin or 20.0) / 100.0
            rg = (peer.revenue_growth or 5.0) / 100.0
            de = peer.debt_equity or 1.0

            raw = (
                (1 / pe) * 0.3 +
                gm * 0.3 +
                rg * 0.2 +
                (1 / max(de, 0.01)) * 0.2
            )
            scored.append({"ticker": peer.ticker, "raw": raw, "peer": peer})

        if not scored:
            return []

        min_s = min(s["raw"] for s in scored)
        max_s = max(s["raw"] for s in scored)
        rng = max_s - min_s or 1.0

        return [
            {
                "ticker": s["ticker"],
                "composite_score": round(((s["raw"] - min_s) / rng) * 100, 1),
                "reason": (
                    f"PE {self._fmt(s['peer'].pe_ratio)}, "
                    f"gross margin {self._fmt(s['peer'].gross_margin, pct=True)}, "
                    f"revenue growth {self._fmt(s['peer'].revenue_growth, pct=True)}"
                ),
            }
            for s in sorted(scored, key=lambda x: x["raw"], reverse=True)
        ]


peer_analyzer = PeerAnalyzer()
