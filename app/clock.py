from datetime import datetime, timezone, timedelta
import sqlite3
from app.db import get_db_connection


class ClockService:
    """Deterministic simulated clock service backed by SQLite clock table."""

    @staticmethod
    def get_offset_seconds() -> int:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT offset_seconds FROM clock WHERE id = 1").fetchone()
            if row:
                return int(row["offset_seconds"])
            return 0
        finally:
            conn.close()

    @staticmethod
    def now() -> datetime:
        """Return the current simulated UTC datetime."""
        offset = ClockService.get_offset_seconds()
        # Fixed base time or real time + offset
        real_utc = datetime.now(timezone.utc)
        return real_utc + timedelta(seconds=offset)

    @staticmethod
    def now_iso() -> str:
        """Return current simulated time as standard ISO-8601 UTC string."""
        return ClockService.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def advance_days(days: int) -> datetime:
        """Advance the simulated clock by N days and persist the new offset."""
        if days < 0:
            raise ValueError("Days cannot be negative")
        additional_seconds = days * 86400
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT offset_seconds FROM clock WHERE id = 1").fetchone()
            current_offset = int(row["offset_seconds"]) if row else 0
            new_offset = current_offset + additional_seconds
            now_str = (datetime.now(timezone.utc) + timedelta(seconds=new_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                """
                UPDATE clock
                SET offset_seconds = ?, updated_at = ?
                WHERE id = 1
                """,
                (new_offset, now_str),
            )
            conn.commit()
            return datetime.now(timezone.utc) + timedelta(seconds=new_offset)
        finally:
            conn.close()

    @staticmethod
    def reset_clock() -> None:
        """Reset the clock offset to zero."""
        conn = get_db_connection()
        try:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "UPDATE clock SET offset_seconds = 0, updated_at = ? WHERE id = 1",
                (now_str,),
            )
            conn.commit()
        finally:
            conn.close()


clock = ClockService()
