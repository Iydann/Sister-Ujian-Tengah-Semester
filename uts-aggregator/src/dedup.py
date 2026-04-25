import sqlite3
from datetime import datetime
import os
import json

class DedupStore:
    def __init__(self):
        data_dir = os.getenv("DATA_DIR", "data")  # fallback lokal

        os.makedirs(data_dir, exist_ok=True)

        db_path = os.path.join(data_dir, "events.db")

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            event_id TEXT,
            timestamp TEXT,
            source TEXT,
            payload TEXT,
            processed_at TEXT,
            UNIQUE(topic, event_id)
        )
        """)

        self.conn.commit()

    def insert_event(self, event):
        cur = self.conn.cursor()

        try:
            cur.execute("""
            INSERT INTO events (topic, event_id, timestamp, source, payload, processed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event["topic"],
                event["event_id"],
                self._normalize_timestamp(event["timestamp"]),
                event["source"],
                json.dumps(event["payload"]),
                datetime.utcnow().isoformat()
            ))

            self.conn.commit()
            return True

        except sqlite3.IntegrityError:
            return False

    def get_events(self, topic):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT topic, event_id, timestamp, source, payload
            FROM events
            WHERE topic=?
        """, (topic,))

        rows = cur.fetchall()

        return [
            {
                "topic": r[0],
                "event_id": r[1],
                "timestamp": r[2],
                "source": r[3],
                "payload": self._deserialize_payload(r[4])
            }
            for r in rows
        ]

    def get_topics(self):
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT topic FROM events")
        return [row[0] for row in cur.fetchall()]

    def close(self):
        self.conn.close()

    @staticmethod
    def _deserialize_payload(raw_payload):
        try:
            return json.loads(raw_payload)
        except (TypeError, json.JSONDecodeError):
            return raw_payload

    @staticmethod
    def _normalize_timestamp(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)