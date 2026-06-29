from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClinicalItem(Base):
    __tablename__ = "clinical_items"

    uid: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    def touch_last_seen(self) -> None:
        self.last_seen = datetime.now(timezone.utc)
