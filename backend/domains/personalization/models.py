from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base


class UserReadHistory(Base):
    __tablename__ = "user_read_history"
    __table_args__ = (UniqueConstraint("user_id", "news_id", name="unique_user_news"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"))
    read_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    first_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserKeywordPreference(Base):
    __tablename__ = "user_keyword_preference"
    __table_args__ = (UniqueConstraint("user_id", "word", name="unique_user_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    word: Mapped[str] = mapped_column(String(255))
    preference: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserInterestTopic(Base):
    __tablename__ = "user_interest_topic"
    __table_args__ = (UniqueConstraint("user_id", "topic", name="unique_user_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
