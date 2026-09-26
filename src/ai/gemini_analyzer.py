"""
Gemini AI 法人決策推理模組 (Gemini Analyzer)
整合 google-genai 最新 SDK，具備結構化 JSON 輸出與量化規則備援引擎
"""
from typing import Dict, Any, Optional
import os
import json
import logging
import math
import re
from google import genai
from google.genai import types
from src.ai.prompt_builder import build_stock_analysis_prompt

logger = logging.getLogger(__name__)

class GeminiStockAnalyzer:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.8-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = os.environ.get("GEMINI_MODEL", model)
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Gemini Client 初始化成功 (模型: {self.model})")
            except Exception as e:
                logger.error(f"Gemini Client 初始化失敗: {e}")

    def analyze_stock(self, stock_profile: Dict[str, Any], market_context: Dict[str, Any]) -> Dict[str, Any]:
        """呼叫 Gemini 進行法人級多維度推演，若失敗則調用規則引擎備援"""
        tech = stock_profile.get("technical", {})
        try:
            close_price = float(tech.get("latest_close", 100.0) or 100.0)
            if math.isnan(close_price) or close_price <= 0:
                close_price = 100.0
        except Exception:
            close_price = 100.0

        if not self.client:
            logger.warning("未設定 GEMINI_API_KEY，啟用純量化規則備援引擎")
            fallback_res = self._rule_based_fallback(stock_profile)
            return self._sanitize_result(fallback_res, close_price)

        prompt = build_stock_analysis_prompt(stock_profile, market_context)

        try:
            # 優先嘗試主要模型，遇 503 或高負載時依序降級至備援模型
            models_to_try = list(dict.fromkeys([self.model, "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]))
            resp = None
            last_err = None

            for m in models_to_try:
                try:
                    resp = self.client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2,
                        )
                    )
                    if resp and resp.text:
                        break
                except Exception as ex:
                    last_err = ex
                    logger.warning(f"使用模型 {m} 失敗: {ex}，嘗試下一個模型...")

            if not resp or not resp.text:
                raise Exception(f"所有 Gemini 模型呼叫失敗: {last_err}")

            raw_text = resp.text.strip()
            # 清理可能的 markdown 包裹
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            result_json = json.loads(raw_text.strip())
            logger.info(f"成功取得 {stock_profile.get('name')} 的 Gemini 法人診斷報告")
            return self._sanitize_result(result_json, close_price)
        except Exception as e:
            logger.error(f"Gemini API 分析異常 ({stock_profile.get('name')}): {e}，切換為量化備援")
            fallback_res = self._rule_based_fallback(stock_profile)
            return self._sanitize_result(fallback_res, close_price)

    def _sanitize_result(self, result: Dict[str, Any], close_price: float) -> Dict[str, Any]:
        """遞迴清理診斷結果，若有字串包含 'nan' 或 'null'，以基準股價修正替換"""
        fallback_str = f"{close_price:.1f}" if close_price > 0 else "100.0"

        def _clean_obj(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _clean_obj(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_clean_obj(item) for item in obj]
            elif isinstance(obj, str):
                if re.search(r'\bnan\b', obj, re.IGNORECASE):
                    return re.sub(r'\bnan\b', fallback_str, obj, flags=re.IGNORECASE)
                return obj
            elif isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return close_price
                return obj
            return obj

        return _clean_obj(result)

    def _rule_based_fallback(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """純量化多因子風控備援引擎 (確保 GitHub Actions 永不中斷推播且絕無 NaN)"""
        name = p.get("name", "")
        code = p.get("code", "")
        tech = p.get("technical", {})
        chips = p.get("chips", {})
        sbl = p.get("sbl_short", {})
        day_t = p.get("day_trading", {})
        rev_trap = p.get("revenue_trap", {})
        pledge = p.get("governance_pledge", {})
        cb = p.get("convertible_bond", {})
        peer = p.get("peer_comparison", {})

        close = tech.get("latest_close", 100.0)
        try:
            close = float(close)
            if math.isnan(close) or close <= 0:
                close = 100.0
        except (ValueError, TypeError):
            close = 100.0

        def get_clean_param(key: str, default_val: float) -> float:
            val = tech.get(key)
            if val is None:
                return default_val
            try:
                f = float(val)
                return default_val if (math.isnan(f) or f <= 0) else f
            except (ValueError, TypeError):
                return default_val

        ma20 = get_clean_param("ma20", close)
        ma5 = get_clean_param("ma5", close)
        sup = get_clean_param("support_level", round(close * 0.95, 1))
        res = get_clean_param("resistance_level", round(close * 1.05, 1))

        score = 50

        # 技術面
        if "多頭" in tech.get("ma_trend", ""): score += 15
        elif "空頭" in tech.get("ma_trend", ""): score -= 20
        if "黃金交叉" in tech.get("kd", {}).get("signal", ""): score += 10
        elif "死亡交叉" in tech.get("kd", {}).get("signal", ""): score -= 10

        # 籌碼面
        foreign_5d = chips.get("foreign_5d", 0)
        trust_5d = chips.get("trust_5d", 0)
        if foreign_5d > 500: score += 10
        elif foreign_5d < -500: score -= 10
        if trust_5d > 200: score += 10
        elif trust_5d < -200: score -= 10

        # 借券賣出 SBL
        if sbl.get("sbl_change_5d", 0) <= -500: score += 10
        elif sbl.get("sbl_change_5d", 0) >= 1000: score -= 15

        # 董監質押
        pledge_ratio = pledge.get("pledge_ratio", 0.0)
        if pledge_ratio >= 50.0: score -= 30
        elif pledge_ratio >= 30.0: score -= 15

        # 真假營收陷阱
        if rev_trap.get("is_trap"): score -= 30

        # 當沖比
        dt_ratio = day_t.get("day_trading_ratio", 30.0)
        if dt_ratio >= 55.0: score -= 10

        # 同業比對
        if "領頭羊" in peer.get("role", ""): score += 10
        elif "弱勢掉隊" in peer.get("role", ""): score -= 10

        # 燈號判定
        if score >= 65 and not rev_trap.get("is_trap") and pledge_ratio < 40.0:
            traffic_light = "GREEN"
            is_buy = True
            action_verdict = "多方技術與籌碼結構共振，具攻擊條件，可順勢布局"
            buy_reason = f"股價維持多方軌道 (站上月線 {ma20})，法人籌碼呈偏多布局 (外資5日{foreign_5d:+d}張/投信{trust_5d:+d}張)，無高質押與真假營收疑慮。"
            triggers = ["若開盤跳空開高 > 2% 勿市價追價，拉回 5MA 附近再行承接", "觀察盤中成交量需維持 5 日均量以上"]
        elif score <= 40 or rev_trap.get("is_trap") or pledge_ratio >= 50.0:
            traffic_light = "RED"
            is_buy = False
            action_verdict = "空方結構或風控指標亮警訊，嚴禁躁進，以防禦減碼為主"
            buy_reason = "技術面轉弱或風控雷達檢測到重大隱憂 (如借券賣出擴增、週轉天數惡化或高質押壓力)。"
            triggers = [
                f"股價需放量帶長紅收腳並重新站穩月線 ({ma20} 元) 達 3 日不破",
                "外資與法人借券賣出餘額停止擴大並出現連續 2 日回補逾千張",
                "等待真假營收與存貨週轉疑慮於次季財報獲得實質釐清"
            ]
        else:
            traffic_light = "YELLOW"
            is_buy = False
            action_verdict = "多空訊號拉鋸，處於區間震盪整理，建議暫時觀望等待突破"
            buy_reason = f"均線多空排列尚未明朗或面臨上方整數/前波壓力 ({res} 元)，量能尚未顯著表態。"
            triggers = [
                f"待股價放量突破關鍵壓力位 {res} 元並確認收盤站穩",
                f"回測下方波段重要支撐 {sup} 元不破且出現低檔 KD 黃金交叉",
                "外資與投信出現同步連續 2 日淨買超"
            ]

        # 買入策略設定 (安全防護邊界計算)
        entry_low = round(min(close, ma5) * 0.99, 1)
        entry_high = round(max(close, ma5) * 1.01, 1)
        stop_loss = round(min(sup, close * 0.95), 1)
        target = round(max(res, close * 1.08), 1)

        # 雙重防護：絕不允許 NaN 或 <= 0 出現在點位上
        if math.isnan(entry_low) or entry_low <= 0: entry_low = round(close * 0.98, 1)
        if math.isnan(entry_high) or entry_high <= 0: entry_high = round(close * 1.01, 1)
        if math.isnan(stop_loss) or stop_loss <= 0: stop_loss = round(close * 0.95, 1)
        if math.isnan(target) or target <= 0: target = round(close * 1.08, 1)

        strategy = {
            "entry_price_range": f"{entry_low} ~ {entry_high} 元 (回測5MA不破分批布局)" if is_buy else f"待條件達成於 {entry_low} 元附近分批切入",
            "position_size_pct": "初次試單 15% ~ 20%，突破壓力加碼至 30%" if is_buy else "目前維持 0% 觀望，條件滿足後以 10% 試單",
            "take_profit_target": f"第一目標價 {target} 元 (波段目標前高附近分批獲利了結)",
            "stop_loss_price": f"嚴格停損價 {stop_loss} 元 (跌破即刻執行風險控管離場)",
            "execution_notes": "盤前掛單避免市價追高，注意開盤前 15 分鐘隔日沖與當沖客震盪洗盤。"
        }

        deep_dim = {
            "catalyst_analysis": f"{p.get('sector')} 產業動能驅動，留意近期月營收公布與指標權值法說會指引。",
            "cb_arbitrage_assessment": cb.get("summary", "無發行可轉債"),
            "governance_and_pledge": f"董監質押比率 {pledge.get('pledge_ratio')}% ({pledge.get('risk_level')})，內部人持股正常。",
            "revenue_trap_check": rev_trap.get("comment", "週轉天數正常"),
            "sbl_short_and_chips": f"{chips.get('summary', '')}；借券賣出趨勢: {sbl.get('trend')} ({sbl.get('interpretation', '')})",
            "day_trading_and_flippers": f"當沖比率 {day_t.get('day_trading_ratio')}% ({day_t.get('level')})，{day_t.get('warning')}",
            "peer_and_sector": f"同業表現: {peer.get('role', '')} ({peer.get('comment', '')})"
        }

        return {
            "traffic_light": traffic_light,
            "action_verdict": action_verdict,
            "three_core_questions": {
                "is_buy_time": is_buy,
                "buy_reason": buy_reason,
                "trigger_conditions_to_buy": triggers,
                "buy_strategy": strategy
            },
            "deep_dimensions": deep_dim,
            "ai_institutional_summary": f"【量化晨會結論】{name} ({code}) 今日策略為「{action_verdict}」，請嚴守停損價位 {stop_loss} 元。"
        }
