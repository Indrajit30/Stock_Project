from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

VERSION = "1.0.0"


class CitedPoint(BaseModel):
    text: str
    source: str
    source_url: str


class SnowflakeScores(BaseModel):
    value: float = Field(ge=0, le=10)
    growth: float = Field(ge=0, le=10)
    health: float = Field(ge=0, le=10)
    momentum: float = Field(ge=0, le=10)
    smart_money: float = Field(ge=0, le=10)


class FinancialSnapshot(BaseModel):
    revenue_ttm: float | None = None
    net_income_ttm: float | None = None
    gross_margin: float | None = None
    pe_ratio: float | None = None
    ev_ebitda: float | None = None
    debt_to_equity: float | None = None
    market_cap: float | None = None
    sector: str | None = None
    industry: str | None = None
    revenue_growth_yoy: float | None = None


class StockReport(BaseModel):
    ticker: str
    company_name: str
    verdict: Literal["buy", "wait", "avoid"]
    verdict_confidence: float = Field(ge=0, le=1)
    plain_english_summary: str
    three_bulls: list[CitedPoint]
    three_risks: list[CitedPoint]
    snowflake_scores: SnowflakeScores
    financials: FinancialSnapshot
    generated_at: datetime


class PeerComparisonRow(BaseModel):
    ticker: str
    company_name: str
    market_cap: float | None = None
    pe_ratio: float | None = None
    ev_ebitda: float | None = None
    gross_margin: float | None = None
    revenue_growth_yoy: float | None = None
    net_margin: float | None = None
    debt_to_equity: float | None = None
    snowflake_scores: SnowflakeScores | None = None


class InsiderTrade(BaseModel):
    name: str
    role: str
    shares: float
    value_usd: float
    trade_date: datetime
    is_10b5_plan: bool


class InsiderCluster(BaseModel):
    ticker: str
    cluster_date: datetime
    total_value_usd: float
    insider_count: int
    insiders: list[InsiderTrade]
    signal_strength: float = Field(ge=0, le=1)


class FundEntry(BaseModel):
    fund_name: str
    shares_held: float
    pct_of_fund_aum: float
    change_from_prior: float


class SuperinvestorCluster(BaseModel):
    ticker: str
    quarter: str
    funds: list[FundEntry]
    total_aum_pct: float


class DiffSection(BaseModel):
    section_name: str
    positives: list[str]
    negatives: list[str]
    summary: str


class FilingDiff(BaseModel):
    ticker: str
    filing_type: str
    current_period: str
    prior_period: str
    changed_sections: list[DiffSection]


class RedditPost(BaseModel):
    title: str
    subreddit: str
    score: int
    url: str
    sentiment: float


class SentimentPulse(BaseModel):
    ticker: str
    reddit_score: float = Field(ge=-1, le=1)
    reddit_mention_count: int
    top_posts: list[RedditPost]
    updated_at: datetime
