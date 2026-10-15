#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decision 3.0 × 股票分析 Skill 整合後端服務
提供本地 API 代理以解決 CORS、調用 StockAnalyzer 量化數據、以及調用 Decision 3.0 API 進行買賣判斷。
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error
import ssl
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import webbrowser
import threading
from typing import Dict, Any, List, Optional

# 加入專案路徑
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

from skills.Stock_analysis_skill.scripts.analyzer import StockAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DecisionServer")

DEFAULT_API_KEY = "sk-vsr-I32xzgP5bIpaiXRXFLQkG5T3UDhEhyglqMgAk0deWQY"
DECISION_ENDPOINT = "https://decision.vllm-sr.ai/v1/systemone"
TRACKED_FILE = os.path.join(CURRENT_DIR, "tracked_stocks.json")

# 初始化分析器實例
analyzer = StockAnalyzer()

def get_default_tracked():
    return [
        {"symbol": "2330.TW", "name": "台積電", "market": "TWSE", "note": "晶圓代工龍頭 / AI晶片"},
        {"symbol": "NVDA", "name": "輝達 NVIDIA", "market": "US", "note": "全球AI算力霸主"},
        {"symbol": "TSM", "name": "台積電 ADR", "market": "US", "note": "美股ADR溢折價對照"},
        {"symbol": "2454.TW", "name": "聯發科", "market": "TWSE", "note": "邊緣AI與高階手機晶片"},
        {"symbol": "MU", "name": "美光 Micron", "market": "US", "note": "HBM高頻寬記憶體"},
        {"symbol": "4551.TW", "name": "智伸科", "market": "TWSE", "note": "精密金屬加工 / 汽車醫療"}
    ]

def load_tracked():
    if os.path.exists(TRACKED_FILE):
        try:
            with open(TRACKED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"讀取追蹤清單失敗: {e}")
    default_list = get_default_tracked()
    save_tracked(default_list)
    return default_list

def save_tracked(data):
    try:
        with open(TRACKED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"儲存追蹤清單失敗: {e}")

def build_decision_payload(stock_data: dict, model_name: str = "vllm-sr/d3") -> dict:
    """
    依據股票分析 Skill 產生的多維度量化數據，建構高品質的 Prompt State 與 Decision 3.0 問卷結構
    """
    sym = stock_data.get("symbol", "")
    market = stock_data.get("market", "")
    market_type = stock_data.get("market_type", "TAIWAN")
    tech = stock_data.get("technical", {})
    fund = stock_data.get("fundamentals", {})
    decision = stock_data.get("decision", {})
    traffic_light = decision.get("traffic_light", "YELLOW")
    three_q = decision.get("three_core_questions", {})

    close = tech.get("latest_close", 0)
    change_pct = tech.get("change_pct", 0)
    volume = tech.get("volume", 0)
    vol_ratio = tech.get("volume_ratio_5d", 1.0)
    ma_trend = tech.get("ma_trend", "")
    kd = tech.get("kd", {})
    macd = tech.get("macd", {})
    rsi = tech.get("rsi14", 50)
    support = tech.get("support_level", 0)
    resistance = tech.get("resistance_level", 0)

    # 籌碼面與風控面描述
    state_lines = [
        f"【標的資訊】代號: {sym} ({market})，最新成交價: {close}，今日漲跌幅: {change_pct}%，5日均量比: {vol_ratio}倍。",
        f"【技術矩陣】均線多空趨勢: {ma_trend} (MA5:{tech.get('ma5')}, MA20:{tech.get('ma20')}, MA60:{tech.get('ma60')})。",
        f"【動能指標】KD(9,3,3): K={kd.get('k')}, D={kd.get('d')} ({kd.get('signal')})；MACD狀態: {macd.get('status')} (柱狀體={macd.get('hist')})；RSI(14): {rsi}。",
        f"【波段關鍵位】近20日防守支撐: {support}，波段反彈壓力: {resistance}。"
    ]

    if market_type == "TAIWAN":
        deep = decision.get("deep_dimensions", {})
        chips_text = deep.get("sbl_short_and_chips", "")
        day_trade_text = deep.get("day_trading_and_flippers", "")
        rev_trap_text = deep.get("revenue_trap_check", "")
        pledge_text = deep.get("governance_and_pledge", "")
        cb_text = deep.get("cb_arbitrage_assessment", "")
        catalyst_text = deep.get("catalyst_analysis", "")

        state_lines.append(
            f"【台股法人籌碼與動態】三大法人與借券動態: {chips_text}；當沖熱度: {day_trade_text}。"
        )
        state_lines.append(
            f"【法人風控雷達】最新營收動態: {catalyst_text}；"
            f"真假營收檢測 (DIO/DSO週轉): {rev_trap_text}；"
            f"董監質押斷頭風險: {pledge_text}；"
            f"可轉債 (CB) 套利賣壓: {cb_text}。"
        )
    else:
        # 美股
        state_lines.append(
            f"【美股基本面與機構評級】本益比 P/E: {fund.get('pe_trailing', 'N/A')} (預估 P/E: {fund.get('pe_forward', 'N/A')})；"
            f"毛利率: {fund.get('gross_margin_pct', 'N/A')}%；營收成長率: {fund.get('revenue_growth_pct', 'N/A')}%；"
            f"流通股做空比率 (Short % of Float): {fund.get('short_percent_of_float', 0)}% (做空風險等級: {decision.get('deep_dimensions', {}).get('us_market_depth', {}).get('short_squeeze_risk', '正常')})；"
            f"華爾街分析師平均目標價: {fund.get('analyst_target_price', 'N/A')}；機構評級: {fund.get('recommendation_key', 'N/A')}。"
        )

    # 核心量化初判
    strategy = three_q.get("buy_strategy", {})
    state_lines.append(
        f"【量化模型原始建議】操盤燈號: {traffic_light}，初判結論: {decision.get('action_verdict', '')}。"
        f"建議進場區間: {strategy.get('entry_price_range', '無')}，防守停損價: {strategy.get('stop_loss_price', '無')}，目標停利價: {strategy.get('take_profit_target', '無')}。"
    )

    state_text = "\n".join(state_lines)

    payload = {
        "model": model_name,
        "state": state_text,
        "questions": {
            "action_decision": {
                "type": "choice",
                "instructions": "綜合上述全維度技術動能、法人籌碼、風控雷達與基本面數據，現在對該股票的最優操作決定為何？",
                "criteria": {
                    "buy": "現在是買入或分批佈局的良機，具備明確勝率與多頭支撐",
                    "hold_watch": "暫時觀望等待，等待回測支撐不破或關鍵指標沉澱後再進場",
                    "sell_avoid": "建議賣出或觀望避開，存在短線破線或籌碼風控下行風險"
                }
            },
            "timing_score": {
                "type": "score",
                "instructions": "當前進場買入的時機成熟度與勝率評分為何？",
                "criteria": [
                    "低勝率：逆風且無明確買訊，進場容易套牢",
                    "中勝率：具備部分支撐但需等待確認訊號，僅適合極低部位試單",
                    "高勝率：技術多頭共振、量價齊揚且風控安全，絕佳進場時機"
                ]
            },
            "risk_level": {
                "type": "choice",
                "instructions": "該標的目前面臨的下行或回檔風險程度？",
                "criteria": {
                    "low": "低風險：均線密集支撐，無主力倒貨與基本面陷阱",
                    "medium": "中風險：短線乖離稍大或處於區間震盪整理",
                    "high": "高風險：跌破防守線、籌碼渙散或存在塞貨/斷頭套利隱憂"
                }
            },
            "primary_driver": {
                "type": "choice",
                "instructions": "主導目前多空判斷的核心維度為何？",
                "criteria": {
                    "technical_momentum": "技術面均線與量價動能引導",
                    "institutional_flow": "外資或投信法人籌碼大單流向",
                    "fundamental_growth": "營收獲利與產業基本面驅動",
                    "risk_warning": "風控雷達（塞貨、質押、可轉債或做空比）警訊示警"
                }
            }
        }
    }
    return payload

class RequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        # 加上 CORS 標頭讓瀏覽器無阻礙存取
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _send_json(self, status_code: int, data: Any):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_path = self.path.split("?")[0]
        if parsed_path == "/" or parsed_path == "/index.html":
            html_file = os.path.join(CURRENT_DIR, "index.html")
            if os.path.exists(html_file):
                with open(html_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "index.html not found")
        elif parsed_path == "/api/tracked":
            tracked = load_tracked()
            self._send_json(200, {"success": True, "tracked": tracked})
        elif parsed_path == "/api/health":
            self._send_json(200, {"status": "ok", "service": "Decision 3.0 Stock Intelligence"})
        else:
            self.send_error(404, "Endpoint Not Found")

    def do_POST(self):
        parsed_path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = {}
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON payload: {e}"})
                return

        if parsed_path == "/api/tracked":
            # 更新或儲存追蹤清單
            tracked_list = data.get("tracked", [])
            save_tracked(tracked_list)
            self._send_json(200, {"success": True, "tracked": tracked_list})

        elif parsed_path == "/api/analyze":
            # 執行股票分析 Skill 核心模組
            symbol = data.get("symbol", "").strip()
            if not symbol:
                self._send_json(400, {"error": "Missing 'symbol' parameter"})
                return

            try:
                logger.info(f"開始分析標的: {symbol}")
                stock_data = analyzer.analyze(symbol)
                self._send_json(200, {"success": True, "data": stock_data})
            except Exception as e:
                logger.error(f"分析標的 {symbol} 失敗: {e}", exc_info=True)
                self._send_json(500, {"success": False, "error": str(e), "symbol": symbol})

        elif parsed_path == "/api/decision":
            # 調用 Decision 3.0 API
            symbol = data.get("symbol", "")
            stock_data = data.get("stock_data")
            api_key = data.get("api_key", "").strip() or DEFAULT_API_KEY
            model_name = data.get("model", "vllm-sr/d3")

            if not stock_data:
                # 若未傳入現成數據，現場直接跑一次 analyze
                if not symbol:
                    self._send_json(400, {"error": "Must provide 'stock_data' or 'symbol'"})
                    return
                try:
                    logger.info(f"呼叫 Decision 前先擷取 {symbol} 量化數據...")
                    stock_data = analyzer.analyze(symbol)
                except Exception as e:
                    self._send_json(500, {"error": f"擷取量化數據失敗: {e}"})
                    return

            try:
                payload = build_decision_payload(stock_data, model_name=model_name)
                logger.info(f"發送請求給 Decision 3.0 API ({model_name}) 評估 {symbol}...")

                req_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(
                    DECISION_ENDPOINT,
                    data=req_bytes,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                )

                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, context=ctx, timeout=45) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))

                # 組合回傳資料
                self._send_json(200, {
                    "success": True,
                    "symbol": symbol,
                    "stock_data": stock_data,
                    "decision_raw": resp_data,
                    "state_prompt": payload["state"],
                    "model": model_name
                })
            except urllib.error.HTTPError as he:
                err_content = he.read().decode("utf-8", errors="ignore")
                logger.error(f"Decision API 請求出錯 HTTP {he.code}: {err_content}")
                self._send_json(he.code, {"error": f"Decision API Error ({he.code})", "details": err_content})
            except Exception as e:
                logger.error(f"呼叫 Decision 3.0 發生未預期錯誤: {e}", exc_info=True)
                self._send_json(500, {"error": str(e)})

        elif parsed_path == "/api/batch_evaluate":
            # 一次性評估清單上的股票
            symbols = data.get("symbols", [])
            api_key = data.get("api_key", "").strip() or DEFAULT_API_KEY
            model_name = data.get("model", "vllm-sr/d3")

            results = []
            for sym in symbols:
                try:
                    logger.info(f"批次評估標的: {sym}")
                    s_data = analyzer.analyze(sym)
                    payload = build_decision_payload(s_data, model_name=model_name)
                    req_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    req = urllib.request.Request(
                        DECISION_ENDPOINT,
                        data=req_bytes,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        }
                    )
                    ctx = ssl.create_default_context()
                    with urllib.request.urlopen(req, context=ctx, timeout=45) as resp:
                        d_resp = json.loads(resp.read().decode("utf-8"))

                    results.append({
                        "symbol": sym,
                        "success": True,
                        "stock_data": s_data,
                        "decision": d_resp
                    })
                except Exception as ex:
                    logger.warning(f"批次標的 {sym} 處理異常: {ex}")
                    results.append({
                        "symbol": sym,
                        "success": False,
                        "error": str(ex)
                    })

            self._send_json(200, {"success": True, "results": results})
        else:
            self.send_error(404, "Endpoint Not Found")

def run_server(port=8888):
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    logger.info(f"🚀 Decision 3.0 股票決策服務已在 http://localhost:{port} 啟動！")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("伺服器關閉中...")
        httpd.server_close()

if __name__ == "__main__":
    port = 8888
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)

