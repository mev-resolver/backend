import sqlite3
import time
import json
import logging
import os
from typing import Optional, List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(settings.DATABASE_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL    NOT NULL,
                event_type  TEXT    NOT NULL,
                payload     TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

            CREATE TABLE IF NOT EXISTS attacks (
                attack_id             TEXT PRIMARY KEY,
                victim_tx_hash        TEXT NOT NULL,
                buy_tx_hash           TEXT,
                sell_tx_hash          TEXT,
                confidence            REAL DEFAULT 1.0,
                mitigated             INTEGER DEFAULT 0,
                detection_latency_ms  INTEGER,
                mitigation_latency_ms INTEGER,
                created_at            REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                tx_hash       TEXT PRIMARY KEY,
                sender        TEXT,
                token_in      TEXT,
                token_out     TEXT,
                amount_in     REAL,
                gas_price     INTEGER,
                status        TEXT DEFAULT 'submitted',
                attack_id     TEXT,
                bundle_id     TEXT,
                created_at    REAL NOT NULL,
                etherscan_url TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at DESC);

            CREATE TABLE IF NOT EXISTS bundles (
                bundle_id      TEXT PRIMARY KEY,
                victim_tx_hash TEXT,
                status         TEXT DEFAULT 'pending',
                created_at     REAL NOT NULL,
                submitted_at   REAL,
                confirmed_at   REAL,
                error_message  TEXT
            );
        """)
        conn.commit()
    logger.info("Database initialised at %s", settings.DATABASE_PATH)


def store_event(event_type: str, payload: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (timestamp, event_type, payload) VALUES (?,?,?)",
            (time.time(), event_type, json.dumps(payload))
        )
        conn.commit()
        return cur.lastrowid


def get_events(limit: int = 100, offset: int = 0) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]


def get_events_in_range(start_ts: float, end_ts: float) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp ASC",
            (start_ts, end_ts)
        ).fetchall()
        return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]


def store_attack(attack: dict) -> None:
    with get_conn() as conn:
        conn.execute("""INSERT OR REPLACE INTO attacks
               (attack_id, victim_tx_hash, buy_tx_hash, sell_tx_hash,
                confidence, mitigated, detection_latency_ms, created_at)
               VALUES (:attack_id,:victim_tx_hash,:buy_tx_hash,:sell_tx_hash,
                       :confidence,:mitigated,:detection_latency_ms,:created_at)""",
            attack)
        conn.commit()


def update_attack_mitigated(attack_id: str, mitigation_ms: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE attacks SET mitigated=1, mitigation_latency_ms=? WHERE attack_id=?",
            (mitigation_ms, attack_id)
        )
        conn.commit()


def store_transaction(tx: dict) -> None:
    with get_conn() as conn:
        conn.execute("""INSERT OR REPLACE INTO transactions
               (tx_hash,sender,token_in,token_out,amount_in,gas_price,
                status,attack_id,bundle_id,created_at,etherscan_url)
               VALUES (:tx_hash,:sender,:token_in,:token_out,:amount_in,:gas_price,
                       :status,:attack_id,:bundle_id,:created_at,:etherscan_url)""",
            tx)
        conn.commit()


def update_tx_status(tx_hash: str, status: str, bundle_id: Optional[str] = None) -> None:
    with get_conn() as conn:
        if bundle_id:
            conn.execute("UPDATE transactions SET status=?, bundle_id=? WHERE tx_hash=?",
                         (status, bundle_id, tx_hash))
        else:
            conn.execute("UPDATE transactions SET status=? WHERE tx_hash=?",
                         (status, tx_hash))
        conn.commit()


def get_transactions(limit: int = 50) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def store_bundle(bundle: dict) -> None:
    with get_conn() as conn:
        conn.execute("""INSERT OR REPLACE INTO bundles
               (bundle_id,victim_tx_hash,status,created_at)
               VALUES (:bundle_id,:victim_tx_hash,:status,:created_at)""", bundle)
        conn.commit()


def update_bundle(bundle_id: str, status: str,
                  confirmed_at: Optional[float] = None,
                  error: Optional[str] = None) -> None:
    with get_conn() as conn:
        conn.execute("""UPDATE bundles
               SET status=?,submitted_at=?,confirmed_at=?,error_message=?
               WHERE bundle_id=?""",
            (status, time.time(), confirmed_at, error, bundle_id))
        conn.commit()


def get_summary_stats() -> Dict[str, Any]:
    with get_conn() as conn:
        atk = conn.execute(
            """SELECT COUNT(*) as total, SUM(mitigated) as mitigated,
                      AVG(detection_latency_ms) as avg_det,
                      AVG(mitigation_latency_ms) as avg_mit
               FROM attacks"""
        ).fetchone()
        total_tx  = conn.execute("SELECT COUNT(*) as n FROM transactions").fetchone()['n']
        total_evs = conn.execute("SELECT COUNT(*) as n FROM events").fetchone()['n']

        detected  = int(atk['total'] or 0)
        mitigated = int(atk['mitigated'] or 0)
        return {
            "total_attacks_detected":  detected,
            "total_attacks_mitigated": mitigated,
            "success_rate": round(mitigated / detected * 100, 1) if detected else 0.0,
            "avg_detection_latency_ms":  round(atk['avg_det'] or 0),
            "avg_mitigation_latency_ms": round(atk['avg_mit'] or 0),
            "total_transactions": total_tx,
            "total_events": total_evs,
        }
