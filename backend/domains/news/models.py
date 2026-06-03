from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...database import Base


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    article_data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))

    keywords: Mapped[list["ArticleKeyword"]] = relationship(
        back_populates="news",
        cascade="all, delete-orphan",
    )
    analysis: Mapped["NewsAnalysis | None"] = relationship(
        back_populates="news",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Keyword(Base):
    __tablename__ = "keyword"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    article_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    news_links: Mapped[list["ArticleKeyword"]] = relationship(
        back_populates="keyword",
        cascade="all, delete-orphan",
    )


class ArticleKeyword(Base):
    __tablename__ = "article_keyword"
    __table_args__ = (UniqueConstraint("news_id", "keyword_id", name="unique_news_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"))
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keyword.id", ondelete="CASCADE"))
    count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    news: Mapped[News] = relationship(back_populates="keywords")
    keyword: Mapped[Keyword] = relationship(back_populates="news_links")


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"), unique=True)
    summary: Mapped[str] = mapped_column(Text)
    ad_probability: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0, server_default="0.00")
    is_clickbait: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    named_entities: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))

    news: Mapped[News] = relationship(back_populates="analysis")
