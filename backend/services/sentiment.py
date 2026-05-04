import asyncio
import logging
from datetime import datetime, timezone

import httpx

from shared.schemas import RedditPost, SentimentPulse

logger = logging.getLogger(__name__)

REDDIT_HEADERS = {"User-Agent": "StockResearchApp/1.0 research@example.com"}
SUBREDDITS = ["wallstreetbets", "stocks", "investing"]


async def get_reddit_sentiment(ticker: str) -> SentimentPulse:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()
    all_posts: list[RedditPost] = []
    weighted_score = 0.0
    weight_total = 0.0

    async with httpx.AsyncClient(headers=REDDIT_HEADERS, timeout=15) as client:
        urls = [
            f"https://www.reddit.com/search.json?q={ticker}&sort=hot&limit=25&t=week",
            *[
                f"https://www.reddit.com/r/{sub}/search.json?q={ticker}&sort=hot&limit=10&restrict_sr=1&t=week"
                for sub in SUBREDDITS
            ],
        ]

        async def _fetch(url: str):
            try:
                resp = await client.get(url)
                return resp.json()
            except Exception as exc:
                logger.warning("Reddit fetch failed %s: %s", url, exc)
                return {}

        responses = await asyncio.gather(*[_fetch(u) for u in urls])

    for data in responses:
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            title = post.get("title", "")
            body = post.get("selftext", "")
            text = f"{title} {body}".strip()
            score = int(post.get("score", 0))
            subreddit = post.get("subreddit", "")
            url = f"https://reddit.com{post.get('permalink', '')}"

            compound = analyzer.polarity_scores(text)["compound"]
            weight = max(score, 1)
            weighted_score += compound * weight
            weight_total += weight

            all_posts.append(
                RedditPost(
                    title=title,
                    subreddit=subreddit,
                    score=score,
                    url=url,
                    sentiment=round(compound, 3),
                )
            )

    final_score = round(weighted_score / weight_total, 4) if weight_total else 0.0
    top_posts = sorted(all_posts, key=lambda p: p.score, reverse=True)[:5]

    return SentimentPulse(
        ticker=ticker,
        reddit_score=max(-1.0, min(1.0, final_score)),
        reddit_mention_count=len(all_posts),
        top_posts=top_posts,
        updated_at=datetime.now(timezone.utc),
    )


async def get_apewisdom_rank(ticker: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://apewisdom.io/api/v1.0/filter/all-stocks/")
            data = resp.json()
            results = data.get("results", [])
            for item in results:
                if item.get("ticker", "").upper() == ticker.upper():
                    return {
                        "rank": item.get("rank"),
                        "mention_count": item.get("mentions"),
                        "upvotes_24h": item.get("upvotes"),
                    }
    except Exception as exc:
        logger.warning("ApeWisdom fetch failed for %s: %s", ticker, exc)
    return {"rank": None, "mention_count": 0, "upvotes_24h": 0}


async def get_full_sentiment(ticker: str) -> SentimentPulse:
    pulse, ape = await asyncio.gather(
        get_reddit_sentiment(ticker),
        get_apewisdom_rank(ticker),
    )
    # Merge mention count hint from ape wisdom
    if ape.get("mention_count"):
        pulse = pulse.model_copy(
            update={"reddit_mention_count": pulse.reddit_mention_count + int(ape["mention_count"])}
        )
    return pulse
