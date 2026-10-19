"""
TW_STOCK_DECISION - 結論與預測準確度追蹤系統 (Decision Tracker & Review DB)
記錄每天早盤 (10:00) 預測與午盤 (14:00) 結算比對，提供每週準確度統整分析
"""
import os
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta

logger = logging.getLogger("DecisionTracker")

class DecisionTracker:
    def __init__(self, db_path: str = "data/decisions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化資料表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    market TEXT,
                    morning_time TEXT,
                    morning_price REAL,
                    morning_decision TEXT,
                    morning_confidence REAL,
                    morning_reason TEXT,
                    afternoon_time TEXT,
                    afternoon_price REAL,
                    day_change REAL,
                    day_change_pct REAL,
                    is_concluded INTEGER DEFAULT 0,
                    conclusion_result TEXT,
                    is_correct INTEGER,
                    review_comment TEXT,
                    raw_morning_json TEXT,
                    raw_afternoon_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, symbol)
                )
            """)
            conn.commit()

    def record_morning_prediction(
        self,
        date_str: str,
        symbol: str,
        name: str,
        market: str,
        price: float,
        decision: str,
        confidence: float,
        reason: str,
        raw_json: dict = None
    ):
        """記錄早上 10:00 的預測"""
        now_time = datetime.now().strftime("%H:%M:%S")
        raw_str = json.dumps(raw_json, ensure_ascii=False) if raw_json else ""
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_decisions (
                    date, symbol, name, market, morning_time, morning_price,
                    morning_decision, morning_confidence, morning_reason, raw_morning_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, symbol) DO UPDATE SET
                    morning_time=excluded.morning_time,
                    morning_price=excluded.morning_price,
                    morning_decision=excluded.morning_decision,
                    morning_confidence=excluded.morning_confidence,
                    morning_reason=excluded.morning_reason,
                    raw_morning_json=excluded.raw_morning_json
            """, (date_str, symbol, name, market, now_time, price, decision, confidence, reason, raw_str))
            conn.commit()
            logger.info(f"[{date_str}] 已記錄早盤預測: {symbol} ({name}) - 決策: {decision} (${price})")

    def record_afternoon_conclusion(
        self,
        date_str: str,
        symbol: str,
        afternoon_price: float,
        day_change: float,
        day_change_pct: float,
        name: str = "",
        raw_json: dict = None
    ) -> Optional[Dict[str, Any]]:
        """
        記錄下午 14:00 收盤結果，並自動判定是否與早盤預測吻合
        """
        now_time = datetime.now().strftime("%H:%M:%S")
        raw_str = json.dumps(raw_json, ensure_ascii=False) if raw_json else ""

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_decisions WHERE date=? AND symbol=?", (date_str, symbol))
            row = cursor.fetchone()
            stock_name = (row["name"] if row and row["name"] else name) or symbol

            if not row or not row["morning_decision"]:
                logger.warning(f"[{date_str}] 未找到早盤預測記錄: {symbol}，僅記錄收盤價")
                cursor.execute("""
                    INSERT INTO daily_decisions (
                        date, symbol, name, afternoon_time, afternoon_price, day_change, day_change_pct, is_concluded
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(date, symbol) DO UPDATE SET
                        name=COALESCE(daily_decisions.name, excluded.name),
                        afternoon_time=excluded.afternoon_time,
                        afternoon_price=excluded.afternoon_price,
                        day_change=excluded.day_change,
                        day_change_pct=excluded.day_change_pct,
                        is_concluded=1
                """, (date_str, symbol, stock_name, now_time, afternoon_price, day_change, day_change_pct))
                conn.commit()
                return {
                    "symbol": symbol,
                    "name": stock_name,
                    "morning_decision": "無早盤預測",
                    "morning_price": 0.0,
                    "afternoon_price": afternoon_price,
                    "price_diff_pct": day_change_pct,
                    "is_correct": False,
                    "is_untracked": True,
                    "conclusion_result": f"收盤價 ${afternoon_price:.2f} ({day_change_pct:+.2f}%)，當日無早盤預測對照",
                    "review_comment": "無早盤預測記錄"
                }

            m_dec = (row["morning_decision"] or "").lower()
            m_price = row["morning_price"] or 0.0

            # 判定準確度邏輯：
            # 1. 買進 (buy):
            #    - 下午價格高於早盤買進價 (下午上漲獲利) 或今日維持強勢收紅 -> 吻合 (True)
            # 2. 賣出/避開 (sell):
            #    - 下午價格低於早盤價 (成功避開下跌) 或收黑跌幅擴大 -> 吻合 (True)
            # 3. 觀望/持有 (hold):
            #    - 盤中振幅狹幅整理 (-1.5% ~ +1.5%) -> 吻合 (True)
            is_correct = 0
            conclusion_text = ""
            review = ""

            price_diff = afternoon_price - m_price
            price_diff_pct = (price_diff / m_price * 100.0) if m_price > 0 else 0.0

            if m_dec in ["buy", "green"]:
                if price_diff > 0 or day_change_pct > 0.5:
                    is_correct = 1
                    conclusion_text = "預測成功 (買進後上漲獲利)"
                    review = f"早盤判斷買進 (${m_price:.1f})，尾盤收高至 ${afternoon_price:.1f} ({price_diff_pct:+.2f}%)，多頭動能延續。"
                else:
                    is_correct = 0
                    conclusion_text = "預測偏差 (買進後回檔走低)"
                    review = f"早盤判斷買進 (${m_price:.1f})，但尾盤走跌至 ${afternoon_price:.1f} ({price_diff_pct:+.2f}%)，觸發回測守穩檢驗。"
            elif m_dec in ["sell", "red"]:
                if price_diff <= 0 or day_change_pct < -0.5:
                    is_correct = 1
                    conclusion_text = "預測成功 (成功避開下跌修正)"
                    review = f"早盤警示賣出/避開 (${m_price:.1f})，尾盤跌至 ${afternoon_price:.1f} ({price_diff_pct:+.2f}%)，有效規避風險。"
                else:
                    is_correct = 0
                    conclusion_text = "預測偏差 (逆勢強彈嘎空)"
                    review = f"早盤預警賣出 (${m_price:.1f})，尾盤逆勢收高至 ${afternoon_price:.1f} ({price_diff_pct:+.2f}%)。"
            else: # hold / yellow
                if abs(price_diff_pct) <= 2.0:
                    is_correct = 1
                    conclusion_text = "預測成功 (如預期處於區間震盪整理)"
                    review = f"早盤建議觀望 (${m_price:.1f})，尾盤收 ${afternoon_price:.1f} ({price_diff_pct:+.2f}%)，多空拉鋸未出方向。"
                else:
                    is_correct = 0
                    conclusion_text = "預測偏差 (盤勢突破整理區間走出單邊)"
                    review = f"早盤評估觀望整理 (${m_price:.1f})，但尾盤出現較大單邊波動 (${afternoon_price:.1f}, {price_diff_pct:+.2f}%)。"

            cursor.execute("""
                UPDATE daily_decisions SET
                    name=COALESCE(name, ?),
                    afternoon_time=?,
                    afternoon_price=?,
                    day_change=?,
                    day_change_pct=?,
                    is_concluded=1,
                    conclusion_result=?,
                    is_correct=?,
                    review_comment=?,
                    raw_afternoon_json=?
                WHERE date=? AND symbol=?
            """, (stock_name, now_time, afternoon_price, day_change, day_change_pct, conclusion_text, is_correct, review, raw_str, date_str, symbol))
            conn.commit()

            return {
                "symbol": symbol,
                "name": stock_name,
                "morning_decision": m_dec,
                "morning_price": m_price,
                "afternoon_price": afternoon_price,
                "price_diff_pct": price_diff_pct,
                "is_correct": bool(is_correct),
                "conclusion_result": conclusion_text,
                "review_comment": review
            }

    def get_daily_conclusion(self, date_str: str) -> List[Dict[str, Any]]:
        """取得當日所有標的的對比結論"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM daily_decisions
                WHERE date=? AND is_concluded=1
                ORDER BY symbol ASC
            """, (date_str,))
            return [dict(row) for row in cursor.fetchall()]

    def get_weekly_summary(self, end_date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        取得過去 7 天 (週一至週五交易日) 的全量預測準確度統整
        """
        if not end_date_str:
            end_date_str = date.today().strftime("%Y-%m-%d")

        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        start_dt = end_dt - timedelta(days=7)
        start_date_str = start_dt.strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM daily_decisions
                WHERE date >= ? AND date <= ? AND is_concluded=1
                ORDER BY date ASC, symbol ASC
            """, (start_date_str, end_date_str))
            rows = [dict(r) for r in cursor.fetchall()]

        total_concluded = len(rows)
        correct_count = sum(1 for r in rows if r["is_correct"] == 1)
        accuracy_pct = (correct_count / total_concluded * 100.0) if total_concluded > 0 else 0.0

        # 按決策類型細分
        buy_records = [r for r in rows if (r.get("morning_decision") or "").lower() in ["buy", "green"]]
        sell_records = [r for r in rows if (r.get("morning_decision") or "").lower() in ["sell", "red"]]
        hold_records = [r for r in rows if (r.get("morning_decision") or "").lower() in ["hold", "yellow", "watch"]]

        def calc_acc(sub_list):
            if not sub_list:
                return 0.0, 0, 0
            corr = sum(1 for r in sub_list if r["is_correct"] == 1)
            return (corr / len(sub_list) * 100.0), corr, len(sub_list)

        buy_acc, buy_c, buy_tot = calc_acc(buy_records)
        sell_acc, sell_c, sell_tot = calc_acc(sell_records)
        hold_acc, hold_c, hold_tot = calc_acc(hold_records)

        # 按每日分組
        daily_breakdown = {}
        for r in rows:
            d = r["date"]
            if d not in daily_breakdown:
                daily_breakdown[d] = {"total": 0, "correct": 0, "records": []}
            daily_breakdown[d]["total"] += 1
            if r["is_correct"] == 1:
                daily_breakdown[d]["correct"] += 1
            daily_breakdown[d]["records"].append(r)

        return {
            "period": f"{start_date_str} ~ {end_date_str}",
            "total_samples": total_concluded,
            "correct_samples": correct_count,
            "accuracy_pct": round(accuracy_pct, 1),
            "breakdown": {
                "buy": {"total": buy_tot, "correct": buy_c, "accuracy": round(buy_acc, 1)},
                "sell": {"total": sell_tot, "correct": sell_c, "accuracy": round(sell_acc, 1)},
                "hold": {"total": hold_tot, "correct": hold_c, "accuracy": round(hold_acc, 1)},
            },
            "daily_breakdown": daily_breakdown,
            "all_records": rows
        }
