"""
TW_STOCK_DECISION - 決策與結論系統排程執行主程式
支援三種排程模式：
1. --mode morning   : 早上 10:00 執行，呼叫 Decision 3.0 API 產出今日買賣預測，存入 DB 並推送到 Discord
2. --mode afternoon : 下午 14:00 執行，抓取收盤結果，比對早盤預測，產出吻合結論報告並推送到 Discord
3. --mode weekly    : 每週六 10:00 執行，統整過去一週預測結果與準確度勝率分析報告並推送到 Discord
"""
import os
import sys
import json
import argparse
import logging
from datetime import datetime, date
from typing import List, Dict, Any

# 加入專案路徑
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

import requests
from src.utils.calendar import is_taiwan_trading_day, get_current_tw_date, get_current_tw_time
from skills.Stock_analysis_skill.scripts.analyzer import StockAnalyzer
from src.decision.tracker import DecisionTracker
from src.decision.discord_builder import DecisionDiscordBuilder
from dashboard.server import build_decision_payload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TW_STOCK_DECISION")

DECISION_API_URL = "https://decision.vllm-sr.ai/v1/systemone"
DEFAULT_DECISION_KEY = "sk-vsr-I32xzgP5bIpaiXRXFLQkG5T3UDhEhyglqMgAk0deWQY"

def load_tracked_stocks() -> List[Dict[str, Any]]:
    """載入觀察清單 (優先載入 dashboard/tracked_stocks.json，若無則載入 config/stocks.yaml)"""
    tracked_path = os.path.join(PROJECT_ROOT, "dashboard", "tracked_stocks.json")
    if os.path.exists(tracked_path):
        try:
            with open(tracked_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception as e:
            logger.warning(f"載入 tracked_stocks.json 失敗: {e}")

    # Fallback 到 config/stocks.yaml
    yaml_path = os.path.join(PROJECT_ROOT, "config", "stocks.yaml")
    if os.path.exists(yaml_path):
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
            tw = y.get("taiwan_stocks", [])
            return [{"symbol": s.get("symbol"), "name": s.get("name"), "market": s.get("market")} for s in tw]

    return [
        {"symbol": "2330.TW", "name": "台積電", "market": "TWSE"},
        {"symbol": "2454.TW", "name": "聯發科", "market": "TWSE"},
        {"symbol": "8069.TWO", "name": "元太", "market": "TPEx"},
        {"symbol": "6669.TW", "name": "緯穎", "market": "TWSE"},
        {"symbol": "3443.TW", "name": "創意", "market": "TWSE"}
    ]

def call_decision_api(stock_data: dict, api_key: str) -> dict:
    """呼叫 Decision 3.0 API 進行買賣判斷"""
    payload = build_decision_payload(stock_data, model_name="vllm-sr/d3")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    resp = requests.post(DECISION_API_URL, headers=headers, json=payload, timeout=25)
    resp.raise_for_status()
    return resp.json()

def _safe_print(text: str):
    """確保在任何作業系統終端機 (含 Windows CP950) 均能安全印出 UTF-8 內容"""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((str(text) + "\n").encode("utf-8", errors="replace"))
            sys.stdout.flush()
        except Exception:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))

def post_discord(embed: dict, webhook_url: str):
    """發送 Discord Embed 訊息，具備乾跑保護、超時重試與錯誤拋出"""
    if not webhook_url or "your_webhook_id" in webhook_url:
        logger.warning("[DRY RUN] 未設定有效 DISCORD_WEBHOOK_URL，輸出卡片內容：")
        try:
            _safe_print(json.dumps(embed, ensure_ascii=False, indent=2))
        except Exception:
            _safe_print(json.dumps(embed, indent=2))
        return

    payload = {
        "username": "TW_STOCK_DECISION",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2936/2936886.png",
        "embeds": [embed]
    }
    headers = {"Content-Type": "application/json"}
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
            if r.status_code in [200, 204]:
                logger.info("Discord Webhook 推送成功！")
                return
            elif r.status_code == 429:
                try:
                    retry_after = float(r.json().get("retry_after", 2.0))
                except Exception:
                    retry_after = 2.0
                logger.warning(f"Discord 觸發頻率限制 (429)，等待 {retry_after} 秒後重試...")
                import time
                time.sleep(retry_after)
            elif r.status_code >= 500:
                logger.warning(f"Discord 伺服器異常 ({r.status_code})，第 {attempt}/{max_retries} 次重試...")
                import time
                time.sleep(2.0 * attempt)
            else:
                logger.error(f"Discord Webhook 推送失敗 ({r.status_code}): {r.text}")
                if attempt == max_retries:
                    raise RuntimeError(f"Discord Webhook 推送失敗 (HTTP {r.status_code}): {r.text}")
                import time
                time.sleep(1.5)
        except Exception as e:
            logger.warning(f"Discord 連線異常 (第 {attempt}/{max_retries} 次): {e}")
            if attempt == max_retries:
                raise RuntimeError(f"Discord Webhook 連線失敗: {e}")
            import time
            time.sleep(2.0 * attempt)

def run_morning(api_key: str, webhook_url: str, custom_stocks: str = "", skip_calendar: bool = False):
    """早上 10:00 執行流程"""
    today_str = get_current_tw_date()
    logger.info(f"=== 執行早盤 10:00 決策分析 ({today_str}) ===")

    if not skip_calendar and not is_taiwan_trading_day():
        logger.info(f"今日 ({today_str}) 非台股開盤日，略過早盤排程。")
        return

    tracker = DecisionTracker()
    builder = DecisionDiscordBuilder()
    analyzer = StockAnalyzer()

    tracked = load_tracked_stocks()
    if custom_stocks:
        custom_symbols = [s.strip() for s in custom_stocks.split(",") if s.strip()]
        tracked = [s for s in tracked if s.get("symbol") in custom_symbols or s.get("code") in custom_symbols]
        if not tracked:
            tracked = [{"symbol": sym, "name": sym} for sym in custom_symbols]

    # 只選取台股 (TWSE / TPEx)
    tw_tracked = [s for s in tracked if ".TW" in s.get("symbol", "") or ".TWO" in s.get("symbol", "") or s.get("symbol", "").isdigit()]
    if not tw_tracked:
        tw_tracked = tracked

    morning_results = []

    for item in tw_tracked:
        sym = item.get("symbol", "")
        name = item.get("name", sym)
        try:
            logger.info(f"正在分析 {sym} ({name})...")
            stock_data = analyzer.analyze(sym)
            tech = stock_data.get("technical", {})
            price = tech.get("latest_close", 0.0)
            chg_pct = tech.get("change_pct", 0.0)

            # 呼叫 Decision 3.0 API
            try:
                dec_resp = call_decision_api(stock_data, api_key)
                ans = dec_resp.get("answers", {})
                act_obj = ans.get("action_decision", {})
                raw_choice = str(act_obj.get("choice", "hold")).lower()
                
                # 標準化決策名稱 (支援 buy / sell_avoid / hold_watch)
                if "buy" in raw_choice:
                    decision = "buy"
                    dec_text = "【建議買進】多頭結構明確，順勢分批布局"
                elif "sell" in raw_choice or "avoid" in raw_choice:
                    decision = "sell"
                    dec_text = "【建議避開】技術弱勢破線，嚴禁盲目追價"
                else:
                    decision = "hold"
                    dec_text = "【觀望等待】多空拉鋸震盪，等待方向確認"

                confidence = act_obj.get("confidence", 0.6)
                risk_choice = ans.get("risk_level", {}).get("choice", "normal")
                
                # 提示風控風險與主要動能
                driver_choice = ans.get("primary_driver", {}).get("choice", "")
                driver_map = {
                    "technical_momentum": "技術動能引導",
                    "institutional_flow": "法人籌碼流向",
                    "fundamental_growth": "基本營收動能",
                    "risk_warning": "風控賣壓警戒"
                }
                driver_desc = driver_map.get(driver_choice, "全維度綜合考量")
                
                reason = f"{dec_text} (核心主因: {driver_desc} | 風險: {risk_choice})"
            except Exception as e:
                logger.warning(f"Decision 3.0 呼叫異常，使用量化備援: {e}")
                q_dec = stock_data.get("decision", {})
                tl = q_dec.get("traffic_light", "YELLOW")
                decision = "buy" if tl == "GREEN" else ("sell" if tl == "RED" else "hold")
                confidence = 0.5
                reason = q_dec.get("action_verdict", "量化動能推估")
                dec_resp = {"fallback": True}

            # 記錄到 DB
            tracker.record_morning_prediction(
                date_str=today_str,
                symbol=sym,
                name=stock_data.get("name", name),
                market=stock_data.get("market", "TWSE"),
                price=price,
                decision=decision,
                confidence=confidence,
                reason=reason,
                raw_json=dec_resp
            )

            morning_results.append({
                "symbol": sym,
                "name": stock_data.get("name", name),
                "price": price,
                "change_pct": chg_pct,
                "decision": decision,
                "confidence": confidence,
                "reason": reason
            })

        except Exception as e:
            logger.error(f"分析 {sym} 失敗: {e}")

    # 發布 Discord 卡片
    if morning_results:
        embed = builder.build_morning_decision_embed(today_str, morning_results)
        post_discord(embed, webhook_url)
    else:
        logger.warning("無任何有效早盤決策產生。")

def run_afternoon(webhook_url: str, custom_stocks: str = "", skip_calendar: bool = False):
    """下午 14:00 執行流程"""
    today_str = get_current_tw_date()
    logger.info(f"=== 執行盤後 14:00 預測結論比對 ({today_str}) ===")

    if not skip_calendar and not is_taiwan_trading_day():
        logger.info(f"今日 ({today_str}) 非台股開盤日，略過盤後排程。")
        return

    tracker = DecisionTracker()
    builder = DecisionDiscordBuilder()
    analyzer = StockAnalyzer()

    # 從 DB 找出今日早上已經預測的標的
    with tracker._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_decisions WHERE date=? AND morning_decision IS NOT NULL", (today_str,))
        morning_rows = [dict(r) for r in cursor.fetchall()]

    if not morning_rows:
        logger.warning(f"今日 ({today_str}) 尚無早盤預測記錄，嘗試以觀察清單更新。")
        tracked = load_tracked_stocks()
        if custom_stocks:
            custom_symbols = [s.strip() for s in custom_stocks.split(",") if s.strip()]
            tracked = [s for s in tracked if s.get("symbol") in custom_symbols or s.get("code") in custom_symbols]
            if not tracked:
                tracked = [{"symbol": sym, "name": sym} for sym in custom_symbols]
        symbols_to_check = [s.get("symbol") for s in tracked if ".TW" in s.get("symbol", "") or ".TWO" in s.get("symbol", "") or s.get("symbol", "").isdigit()]
        if not symbols_to_check:
            symbols_to_check = [s.get("symbol") for s in tracked]
    else:
        if custom_stocks:
            custom_symbols = [s.strip() for s in custom_stocks.split(",") if s.strip()]
            symbols_to_check = [r["symbol"] for r in morning_rows if r["symbol"] in custom_symbols or any(c in r["symbol"] for c in custom_symbols)]
            if not symbols_to_check:
                symbols_to_check = [r["symbol"] for r in morning_rows]
        else:
            symbols_to_check = [r["symbol"] for r in morning_rows]

    afternoon_conclusions = []

    for sym in symbols_to_check:
        try:
            # 抓取收盤價
            stock_data = analyzer.analyze(sym)
            tech = stock_data.get("technical", {})
            close_price = tech.get("latest_close", 0.0)
            chg = tech.get("change", 0.0)
            chg_pct = tech.get("change_pct", 0.0)

            stock_name = stock_data.get("name") or sym
            # 比對並記錄結論
            res = tracker.record_afternoon_conclusion(
                date_str=today_str,
                symbol=sym,
                afternoon_price=close_price,
                day_change=chg,
                day_change_pct=chg_pct,
                name=stock_name,
                raw_json=stock_data
            )
            if res:
                afternoon_conclusions.append(res)
        except Exception as e:
            logger.error(f"結算 {sym} 失敗: {e}")

    # 發布結論 Embed
    if afternoon_conclusions:
        embed = builder.build_afternoon_conclusion_embed(today_str, afternoon_conclusions)
        post_discord(embed, webhook_url)
    else:
        logger.warning("無有效結論數據。")

def run_weekly(webhook_url: str):
    """每週六 10:00 執行全週勝率統整流程"""
    today_str = get_current_tw_date()
    logger.info(f"=== 執行每週六 10:00 決策準確度統整報告 ({today_str}) ===")

    tracker = DecisionTracker()
    builder = DecisionDiscordBuilder()

    summary_data = tracker.get_weekly_summary(end_date_str=today_str)
    embed = builder.build_weekly_summary_embed(summary_data)
    post_discord(embed, webhook_url)

def main():
    parser = argparse.ArgumentParser(description="TW_STOCK_DECISION 自動化決策與結論排程系統")
    parser.add_argument("--mode", choices=["morning", "afternoon", "weekly"], required=True,
                        help="執行模式：morning (早盤10點)、afternoon (盤後14點)、weekly (週六10點)")
    parser.add_argument("--custom-stocks", type=str, default="", help="自訂股票代號 (逗號分隔)")
    parser.add_argument("--skip-calendar-check", action="store_true", help="強制執行，略過交易日檢查")
    parser.add_argument("--api-key", type=str, default="", help="Decision 3.0 API Key")
    parser.add_argument("--webhook-url", type=str, default="", help="Discord Webhook URL")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("DECISION_API_KEY") or DEFAULT_DECISION_KEY
    webhook_url = args.webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")

    if args.mode == "morning":
        run_morning(api_key, webhook_url, args.custom_stocks, args.skip_calendar_check)
    elif args.mode == "afternoon":
        run_afternoon(webhook_url, args.custom_stocks, args.skip_calendar_check)
    elif args.mode == "weekly":
        run_weekly(webhook_url)

if __name__ == "__main__":
    main()
