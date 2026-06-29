from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MovementEvent(Base):
    __tablename__ = "movement_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    gauze_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tools_missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
