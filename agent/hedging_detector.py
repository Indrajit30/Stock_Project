import logging
import re
import statistics
from typing import Optional

from agent.llm_router import llm_router

logger = logging.getLogger(__name__)

HEDGING_WORDS = [
    "uncertain", "challenging", "headwinds", "volatile", "may", "might", "could",
    "potentially", "subject to", "risk", "difficult", "macro", "environment",
    "we'll see", "too early to say", "monitor", "cautious", "careful",
    "we hope", "we expect to", "pending",
]

DEFLECTION_PHRASES = [
    "I'll have to get back to you",
    "we'll follow up on that",
    "that's something we're still evaluating",
    "I don't want to get ahead of ourselves",
    "we'll provide more color later",
]

_SPEAKER_RE = re.compile(
    r'^(Analyst|CEO|CFO|Operator|Moderator|[A-Z][a-z]+\s[A-Z][a-z]+)\s*[:—]',
    re.MULTILINE,
)


class HedgingDetector:
    def parse_transcript_sections(self, transcript_text: str) -> dict:
        lower = transcript_text.lower()
        qa_start = max(
            lower.find("question-and-answer"),
            lower.find("q&a session"),
            lower.find("questions from"),
            lower.find("open the floor"),
        )

        if qa_start == -1:
            prepared, qa = transcript_text, ""
        else:
            prepared = transcript_text[:qa_start]
            qa = transcript_text[qa_start:]

        ceo_chunks, cfo_chunks, analyst_questions = [], [], []
        current_speaker: Optional[str] = None
        current_text: list[str] = []

        for line in transcript_text.splitlines():
            m = _SPEAKER_RE.match(line)
            if m:
                if current_speaker and current_text:
                    block = " ".join(current_text)
                    spkr = current_speaker.lower()
                    if "ceo" in spkr or "chief executive" in spkr:
                        ceo_chunks.append(block)
                    elif "cfo" in spkr or "chief financial" in spkr:
                        cfo_chunks.append(block)
                    elif "analyst" in spkr:
                        analyst_questions.append(block)
                current_speaker = m.group(1)
                current_text = [line[m.end():].strip()]
            elif current_speaker:
                current_text.append(line.strip())

        return {
            "prepared": prepared,
            "qa": qa,
            "ceo_text": " ".join(ceo_chunks),
            "cfo_text": " ".join(cfo_chunks),
            "analyst_questions": analyst_questions,
        }

    def compute_hedging_score(self, text: str) -> float:
        if not text:
            return 0.0
        words = text.lower().split()
        word_count = max(len(words), 1)
        hedge_hits = sum(text.lower().count(w) for w in HEDGING_WORDS)
        # 50 hedges per 1000 words = 1.0
        return min((hedge_hits / word_count) * 1000 / 50.0, 1.0)

    def compute_deflection_count(self, qa_text: str) -> int:
        lower = qa_text.lower()
        return sum(lower.count(phrase.lower()) for phrase in DEFLECTION_PHRASES)

    def compare_to_prior_quarters(
        self, current_score: float, historical_scores: list[float]
    ) -> dict:
        if not historical_scores:
            return {"z_score": 0.0, "trend": "stable", "interpretation": "No historical data"}

        mean = statistics.mean(historical_scores)
        std = statistics.stdev(historical_scores) if len(historical_scores) > 1 else 0.0
        z_score = (current_score - mean) / std if std > 0 else 0.0

        if z_score > 1.5:
            trend, interp = "increasing", (
                "Significantly more hedging than usual — management appears more cautious."
            )
        elif z_score < -1.5:
            trend, interp = "decreasing", (
                "Significantly less hedging than usual — management appears more confident."
            )
        else:
            trend, interp = "stable", "Hedging language is consistent with prior quarters."

        return {"z_score": round(z_score, 2), "trend": trend, "interpretation": interp}

    async def analyze_transcript(
        self,
        ticker: str,
        transcript: str,
        historical_transcripts: Optional[list[str]] = None,
    ) -> dict:
        if not transcript:
            return {
                "hedging_score": 0.0, "ceo_hedging": 0.0, "cfo_hedging": 0.0,
                "deflection_count": 0, "prepared_vs_qa_divergence": 0.0,
                "trend": {}, "interpretation": "No transcript available.",
            }

        sections = self.parse_transcript_sections(transcript)

        current_hedging = self.compute_hedging_score(transcript)
        ceo_hedging = self.compute_hedging_score(sections["ceo_text"])
        cfo_hedging = self.compute_hedging_score(sections["cfo_text"])
        deflections = self.compute_deflection_count(sections["qa"])

        prepared_sentiment = self._finbert_or_vader(sections["prepared"][:512])
        qa_sentiment = self._finbert_or_vader(sections["qa"][:512])

        trend = {}
        if historical_transcripts:
            hist_scores = [self.compute_hedging_score(t) for t in historical_transcripts[-4:]]
            trend = self.compare_to_prior_quarters(current_hedging, hist_scores)

        interp_prompt = (
            f"Earnings call hedging analysis for {ticker}:\n"
            f"- Hedging score: {current_hedging:.2f}/1.0 (higher = more hedging)\n"
            f"- CEO hedging: {ceo_hedging:.2f}, CFO hedging: {cfo_hedging:.2f}\n"
            f"- Analyst questions deflected: {deflections}\n"
            f"- Prepared remarks sentiment: {prepared_sentiment}\n"
            f"- Q&A sentiment: {qa_sentiment}\n"
            f"- Trend vs prior 4 quarters: {trend}\n\n"
            f"In 2-3 sentences, interpret what this means for investors. Be specific about "
            f"what management seems reluctant to discuss directly."
        )
        interpretation = await llm_router.complete_fast(interp_prompt)

        prep_score = prepared_sentiment.get("score", 0.5) if isinstance(prepared_sentiment, dict) else 0.5
        qa_score = qa_sentiment.get("score", 0.5) if isinstance(qa_sentiment, dict) else 0.5

        return {
            "hedging_score": current_hedging,
            "ceo_hedging": ceo_hedging,
            "cfo_hedging": cfo_hedging,
            "deflection_count": deflections,
            "prepared_vs_qa_divergence": abs(prep_score - qa_score),
            "trend": trend,
            "interpretation": interpretation,
        }

    def _finbert_or_vader(self, text: str) -> dict:
        if not text.strip():
            return {"label": "neutral", "score": 0.5}
        try:
            from transformers import pipeline as hf_pipeline
            finbert = hf_pipeline("text-classification", model="ProsusAI/finbert")
            return finbert(text)[0]
        except Exception:
            pass
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            scores = SentimentIntensityAnalyzer().polarity_scores(text)
            compound = scores["compound"]
            label = "positive" if compound > 0.05 else "negative" if compound < -0.05 else "neutral"
            return {"label": label, "score": (compound + 1) / 2}
        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            return {"label": "neutral", "score": 0.5}
