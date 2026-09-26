"""
Stock_analysis_skill - 全維度法人級台美股分析核心模組 (StockAnalyzer)
支援輸入任一台股或美股代號，自動判斷市場並輸出技術面、籌碼面、風控雷達與操盤決策報告。
"""
from typing import Dict, Any, Optional, List
import os
import sys
import json
import logging
import math
import re
from datetime import datetime

# 導入專案數據擷取模組
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import yfinance as yf
from src.data.market_data import MarketDataClient, clean_float
from src.data.finmind_client import FinMindClient
from src.data.twse_client import TWSEOpenDataClient
from src.ai.gemini_analyzer import GeminiStockAnalyzer

logger = logging.getLogger("StockAnalysisSkill")

class StockAnalyzer:
    """全維度股票量化與 AI 法人診斷引擎"""

    def __init__(self, gemini_api_key: Optional[str] = None, finmind_token: Optional[str] = None):
        self.market_client = MarketDataClient()
        self.finmind_client = FinMindClient(api_token=finmind_token)
        self.twse_client = TWSEOpenDataClient()
        self.gemini_analyzer = GeminiStockAnalyzer(api_key=gemini_api_key)

    def resolve_symbol(self, raw_input: str) -> Dict[str, Any]:
        """
        智慧解析股票代號：
        - 4位數字 (如 2330, 1785) -> 自動比對 TWSE (.TW) 或 TPEx (.TWO)
        - 帶有後綴 (如 2330.TW, 1785.TWO) -> 識別為台股
        - 英文字母 (如 NVDA, MU, TSM, AAPL, SPY) -> 識別為美股
        """
        sym = raw_input.strip().upper()

        # 1. 已經帶有台股後綴
        if sym.endswith(".TW"):
            code = sym.replace(".TW", "")
            return {"symbol": sym, "code": code, "market": "TWSE", "type": "TAIWAN", "currency": "TWD"}
        if sym.endswith(".TWO"):
            code = sym.replace(".TWO", "")
            return {"symbol": sym, "code": code, "market": "TPEx", "type": "TAIWAN", "currency": "TWD"}

        # 2. 純數字代號 (台股)
        if sym.isdigit():
            # 優先嘗試上市 (.TW)
            tw_sym = f"{sym}.TW"
            two_sym = f"{sym}.TWO"
            try:
                t_tw = yf.Ticker(tw_sym)
                h = t_tw.history(period="5d")
                if not h.empty and len(h.dropna(subset=['Close'])) > 0:
                    return {"symbol": tw_sym, "code": sym, "market": "TWSE", "type": "TAIWAN", "currency": "TWD"}
            except Exception:
                pass

            # 若上市失敗或上櫃代號前綴 (如 17, 80, 52, 64, 83 等) 測試上櫃
            try:
                t_two = yf.Ticker(two_sym)
                h2 = t_two.history(period="5d")
                if not h2.empty and len(h2.dropna(subset=['Close'])) > 0:
                    return {"symbol": two_sym, "code": sym, "market": "TPEx", "type": "TAIWAN", "currency": "TWD"}
            except Exception:
                pass

            # 預設為上市
            return {"symbol": tw_sym, "code": sym, "market": "TWSE", "type": "TAIWAN", "currency": "TWD"}

        # 3. 英文字母代號 (美股 / ETF / ADR)
        return {"symbol": sym, "code": sym, "market": "US", "type": "US", "currency": "USD"}

    def _collect_us_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """取得美股基本面、估值、放空比率與分析師目標價"""
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            
            short_pct = info.get("shortPercentOfFloat", 0.0)
            if short_pct is not None and not math.isnan(float(short_pct)):
                short_ratio_pct = round(float(short_pct) * 100, 2)
            else:
                short_ratio_pct = 0.0

            gross_margin = info.get("grossMargins", 0.0)
            if gross_margin is not None and not math.isnan(float(gross_margin)):
                gross_margin_pct = round(float(gross_margin) * 100, 2)
            else:
                gross_margin_pct = 0.0

            rev_growth = info.get("revenueGrowth", 0.0)
            if rev_growth is not None and not math.isnan(float(rev_growth)):
                rev_growth_pct = round(float(rev_growth) * 100, 2)
            else:
                rev_growth_pct = 0.0

            target_mean = clean_float(info.get("targetMeanPrice"), 0.0)
            pe_trailing = clean_float(info.get("trailingPE"), 0.0)
            pe_forward = clean_float(info.get("forwardPE"), 0.0)

            return {
                "name": info.get("shortName") or info.get("longName") or symbol,
                "sector": info.get("sector", "科技與綜合類股"),
                "industry": info.get("industry", ""),
                "pe_trailing": pe_trailing,
                "pe_forward": pe_forward,
                "gross_margin_pct": gross_margin_pct,
                "revenue_growth_pct": rev_growth_pct,
                "short_percent_of_float": short_ratio_pct,
                "analyst_target_price": target_mean,
                "recommendation_key": info.get("recommendationKey", "none").upper(),
                "market_cap": info.get("marketCap", 0)
            }
        except Exception as e:
            logger.warning(f"擷取美股 {symbol} 基本面失敗: {e}")
            return {
                "name": symbol,
                "sector": "美股",
                "industry": "",
                "pe_trailing": 0.0,
                "pe_forward": 0.0,
                "gross_margin_pct": 0.0,
                "revenue_growth_pct": 0.0,
                "short_percent_of_float": 0.0,
                "analyst_target_price": 0.0,
                "recommendation_key": "NONE",
                "market_cap": 0
            }

    def _analyze_us_stock_decision(self, tech: Dict[str, Any], us_fund: Dict[str, Any]) -> Dict[str, Any]:
        """美股專屬量化操盤推演引擎"""
        close = clean_float(tech.get("latest_close"), 100.0)
        ma5 = clean_float(tech.get("ma5"), close)
        ma20 = clean_float(tech.get("ma20"), close)
        sup = clean_float(tech.get("support_level"), round(close * 0.95, 2))
        res = clean_float(tech.get("resistance_level"), round(close * 1.05, 2))
        target_analyst = clean_float(us_fund.get("analyst_target_price"), 0.0)

        score = 50

        # 技術趨勢
        if "多頭" in tech.get("ma_trend", ""): score += 20
        elif "空頭" in tech.get("ma_trend", ""): score -= 20
        elif close > ma20: score += 10

        # 動能 KD
        kd_signal = tech.get("kd", {}).get("signal", "")
        if "黃金交叉" in kd_signal: score += 10
        elif "死亡交叉" in kd_signal: score -= 10

        # 估值與成長
        if us_fund.get("gross_margin_pct", 0) >= 50.0: score += 10
        if us_fund.get("revenue_growth_pct", 0) >= 15.0: score += 10
        if us_fund.get("short_percent_of_float", 0) >= 12.0: score -= 15

        # 華爾街目標價
        if target_analyst > close * 1.1: score += 10
        elif target_analyst > 0 and target_analyst < close: score -= 10

        if score >= 65:
            traffic_light = "GREEN"
            is_buy = True
            action = f"股價多頭強勢上攻，站上20MA ({ma20})，成長動能與估值健康，順勢分批布局"
            reason = f"均線多頭結構明確，產業毛利率高達 {us_fund.get('gross_margin_pct')}%，華爾街平均目標價 ${target_analyst} 提供充足潛在上行空間。"
            triggers = [f"回測 5MA (${ma5}) 獲支撐確認後分批切入", "盤中突破前高壓力時順勢加碼"]
        elif score <= 40:
            traffic_light = "RED"
            is_buy = False
            action = "均線破位或短期估值修正壓力沉重，建議避開防禦或逢高減碼"
            reason = f"技術面弱勢跌破月線 (${ma20})，動能轉弱，需防範進一步回檔風險。"
            triggers = [f"需放量長紅重回月線 (${ma20}) 之上維持 3 日", "等待做空比率降低或獲利預估上修"]
        else:
            traffic_light = "YELLOW"
            is_buy = False
            action = "多空拉鋸處於區間震盪整理，建議暫時觀望等待方向確認"
            reason = f"股價在關鍵支撐 (${sup}) 與壓力 (${res}) 之間整理，等待突破信號。"
            triggers = [f"帶量實體紅K突破上方關鍵壓力位 ${res}", f"拉回守穩波段關鍵支撐 ${sup} 且出現 KD 低檔黃金交叉"]

        entry_low = round(min(close, ma5) * 0.99, 2)
        entry_high = round(max(close, ma5) * 1.01, 2)
        stop_loss = round(min(sup, close * 0.95), 2)
        target = round(max(res, target_analyst if target_analyst > 0 else close * 1.10), 2)

        return {
            "traffic_light": traffic_light,
            "action_verdict": action,
            "three_core_questions": {
                "is_buy_time": is_buy,
                "buy_reason": reason,
                "trigger_conditions_to_buy": triggers,
                "buy_strategy": {
                    "entry_price_range": f"${entry_low} ~ ${entry_high}" if is_buy else f"待條件達成於 ${entry_low} 附近分批介入",
                    "position_size_pct": "初次試單 15% ~ 20%，突破壓力加碼至 30%" if is_buy else "目前維持 0% 觀望，條件滿足後以 10% 試單",
                    "take_profit_target": f"第一目標價 ${target} (波段目標前高或分析師目標價附近獲利了結)",
                    "stop_loss_price": f"嚴格停損價 ${stop_loss} (跌破即刻執行風險控管離場)",
                    "execution_notes": "美股開盤前 30 分鐘波動劇烈，避免市價追高，掛單於均線支撐處低接。"
                }
            },
            "deep_dimensions": {
                "catalyst_analysis": f"{us_fund.get('sector')} 龍頭地位驅動，關注財報公布與指引更新。",
                "cb_arbitrage_assessment": "美股標的無台灣可轉債套利賣壓，關注公開市場空單動向。",
                "governance_and_pledge": "美股監管體系內部人持股揭露健全，機構投資人持股比例高。",
                "revenue_trap_check": f"毛利率 {us_fund.get('gross_margin_pct')}%，營收成長率 {us_fund.get('revenue_growth_pct')}%，財務透明度高。",
                "sbl_short_and_chips": f"市場放空比率 {us_fund.get('short_percent_of_float')}%，{'空單壓力輕微' if us_fund.get('short_percent_of_float', 0) < 5 else '注意空單放空力道'}。",
                "day_trading_and_flippers": "流動性充沛，注意隔夜期貨與美股開盤前盤後跳空。",
                "peer_and_sector": f"所屬 {us_fund.get('sector')} 產業，評級展望為 {us_fund.get('recommendation_key')}。"
            },
            "ai_institutional_summary": f"【美股法人晨會】{us_fund.get('name')} 今日策略「{action}」，嚴守停損價 ${stop_loss}。"
        }

    def analyze(self, symbol_or_code: str) -> Dict[str, Any]:
        """
        全維度單股分析入口：自動辨識台股/美股，聚合所有維度並產生操盤決策
        回傳結構包含完整原始數據、決策推理、JSON 結構與 Markdown 報告
        """
        meta = self.resolve_symbol(symbol_or_code)
        symbol = meta["symbol"]
        code = meta["code"]
        market_type = meta["type"]

        logger.info(f"開始分析標的: {symbol} (市場: {meta['market']}, 類型: {market_type})")

        # 1. 技術面與行情指標 (yfinance)
        tech_data = self.market_client.get_stock_technical_summary(symbol)
        if not tech_data:
            raise ValueError(f"無法取得 {symbol} 的歷史行情數據，請確認代號正確性或市場交易狀態。")

        current_price = tech_data["latest_close"]
        currency = meta["currency"]

        # 2. 依市場類型收集特色風控數據
        if market_type == "TAIWAN":
            # 籌碼面：三大法人
            chips = self.finmind_client.get_institutional_flows(code, days=25)
            # 籌碼面：借券賣出 SBL
            sbl = self.finmind_client.get_short_sale_and_sbl(code, days=30)
            # 籌碼面：當沖比率
            day_t = self.finmind_client.get_day_trading_ratio(code, total_volume_shares=tech_data.get("volume", 0))
            # 基本面：真假營收 DIO/DSO
            rev_trap = self.finmind_client.get_revenue_trap_indicators(code)
            # 基本面：最新月營收
            month_rev = self.finmind_client.get_latest_monthly_revenue(code)
            # 公司治理：董監質押率
            pledge = self.twse_client.get_director_pledge_info(code)
            # 衍生性金融：可轉債 CB 套利賣壓
            cb = self.twse_client.get_convertible_bonds(code, current_stock_price=current_price)

            # 組裝給 AI / 規則引擎的 profile
            profile = {
                "symbol": symbol,
                "code": code,
                "name": code,
                "sector": "台股上市櫃",
                "market": meta["market"],
                "technical": tech_data,
                "chips": chips,
                "sbl_short": sbl,
                "day_trading": day_t,
                "revenue_trap": rev_trap,
                "monthly_revenue": month_rev,
                "governance_pledge": pledge,
                "convertible_bond": cb,
                "peer_comparison": {"role": "台股產業觀察標的", "comment": "關注加權/櫃買指數連動"}
            }

            # 呼叫 Gemini 或純量化備援
            market_context = {"market": "TWSE/TPEx", "analysis_date": datetime.now().strftime("%Y-%m-%d")}
            decision = self.gemini_analyzer.analyze_stock(profile, market_context)
            fundamentals = {
                "monthly_revenue": month_rev,
                "revenue_trap": rev_trap,
                "chips": chips,
                "sbl_short": sbl,
                "day_trading": day_t,
                "governance_pledge": pledge,
                "convertible_bond": cb
            }
        else:
            # 美股基本面與分析師預估
            us_fund = self._collect_us_fundamentals(symbol)
            profile = {
                "symbol": symbol,
                "code": code,
                "name": us_fund.get("name", symbol),
                "sector": us_fund.get("sector", "美股科技/權值"),
                "market": "US",
                "technical": tech_data,
                "fundamentals": us_fund
            }
            # 美股決策引擎
            decision = self._analyze_us_stock_decision(tech_data, us_fund)
            fundamentals = us_fund

        # 3. 生成 Markdown 專業報告
        markdown_report = self._build_markdown_report(profile, decision, fundamentals, currency)

        return {
            "symbol": symbol,
            "code": code,
            "market": meta["market"],
            "market_type": market_type,
            "currency": currency,
            "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "technical": tech_data,
            "fundamentals": fundamentals,
            "decision": decision,
            "markdown_report": markdown_report
        }

    def _build_markdown_report(self, profile: Dict[str, Any], decision: Dict[str, Any], fund: Dict[str, Any], curr: str) -> str:
        """組裝人類與 LLM 均極度易讀的專業法人級 Markdown 報告"""
        sym = profile.get("symbol", "")
        code = profile.get("code", "")
        name = profile.get("name", sym)
        tech = profile.get("technical", {})
        close = tech.get("latest_close", 0.0)
        chg = tech.get("change", 0.0)
        chg_pct = tech.get("change_pct", 0.0)
        chg_sign = "+" if chg > 0 else ""
        icon = "🔺" if chg > 0 else ("🔻" if chg < 0 else "▫️")

        light = decision.get("traffic_light", "YELLOW")
        light_badge = "🟢【積極買入 / 偏多主攻】" if light == "GREEN" else ("🟡【觀望等待 / 震盪整理】" if light == "YELLOW" else "🔴【減碼防禦 / 空方警戒】")

        q = decision.get("three_core_questions", {})
        strat = q.get("buy_strategy", {})
        deep = decision.get("deep_dimensions", {})
        kd = tech.get("kd", {})
        macd = tech.get("macd", {})

        triggers_text = "\n".join([f"  • {t}" for t in q.get("trigger_conditions_to_buy", [])]) if q.get("trigger_conditions_to_buy") else "  • 暫無特殊門檻條件"

        report = f"""# 📊 全維度法人級股票決策報告: {code} {name} ({sym})
> **市場評級**：{light_badge}  
> **最新股價**：`{close} {curr}` ({icon} `{chg_sign}{chg:.2f}` / `{chg_sign}{chg_pct:.2f}%`)  
> **盤前定調**：**{decision.get('action_verdict', '')}**

---

### 🎯【三大核心操盤決策指引】
**1. 現在是不是買入時機？**
👉 **{'【是】' if q.get('is_buy_time') else '【否 / 暫緩】'}**：{q.get('buy_reason')}

**2. 買入觸發條件：**
{triggers_text}

**3. 操盤買入策略：**
* 📍 **建議進場區間**：`{strat.get('entry_price_range', '待條件確認')}`
* 💼 **部位資金配置**：`{strat.get('position_size_pct', '10% ~ 20%')}`
* 🎯 **停利目標價位**：`{strat.get('take_profit_target', '前高壓力處')}`
* 🛡️ **嚴格停損防守**：`{strat.get('stop_loss_price', '跌破支撐即出')}`
* ⚡ **盤中執行提醒**：*{strat.get('execution_notes', '盤初注意洗盤，避免追高')}*

---

### 📈【技術面與動能矩陣】
* **均線多空趨勢**：{tech.get('ma_trend')} (MA5: `{tech.get('ma5')}` | MA10: `{tech.get('ma10')}` | MA20: `{tech.get('ma20')}` | MA60: `{tech.get('ma60')}`)
* **動能指標矩陣**：KD(9,3) `{kd.get('k')}/{kd.get('d')}` ({kd.get('signal')}) | MACD: {macd.get('status')} | RSI(14): `{tech.get('rsi14')}`
* **成交量能分析**：今日量比 5MA `{tech.get('volume_ratio_5d')}x` (成交量: `{tech.get('volume'):,}` 股)
* **波段防守關鍵**：20日關鍵支撐 `{tech.get('support_level')} {curr}` | 20日關鍵壓力 `{tech.get('resistance_level')} {curr}`
"""

        # 區分台股風控雷達與美股基本面
        if "chips" in fund:
            chips = fund["chips"]
            sbl = fund["sbl_short"]
            day_t = fund["day_trading"]
            rev_trap = fund["revenue_trap"]
            month_rev = fund["monthly_revenue"]
            pledge = fund["governance_pledge"]
            cb = fund["convertible_bond"]

            report += f"""
---

### 🛡️【法人高階風控雷達 (台股專屬)】
* **三大法人籌碼**：外資 `{chips.get('foreign_streak')}` (5日淨 `{chips.get('foreign_5d', 0):+d}` 張) | 投信 `{chips.get('trust_streak')}` (5日淨 `{chips.get('trust_5d', 0):+d}` 張)
* **借券賣出餘額 (SBL)**：{sbl.get('risk_tag')} 餘額 `{sbl.get('sbl_balance_lots')}` 張 (5日變動 `{sbl.get('sbl_change_5d', 0):+d}` 張) - *{sbl.get('interpretation')}*
* **當沖比率警示**：{day_t.get('tag')} 當沖佔比 `{day_t.get('day_trading_ratio')}%` - *{day_t.get('warning')}*
* **真假營收 (DIO/DSO)**：{rev_trap.get('tag')} {rev_trap.get('comment')}
* **最新營收動態**：{month_rev.get('summary', '最新月營收穩定')}
* **可轉債 (CB) 套利賣壓**：{cb.get('summary')}
* **董監質押斷頭風險**：{pledge.get('risk_tag')} 董監質押率 `{pledge.get('pledge_ratio')}%` ({pledge.get('risk_level')})
"""
        else:
            report += f"""
---

### 🇺🇸【美股基本面與華爾街動態】
* **估值本益比**：歷史 P/E `{fund.get('pe_trailing')}` | 預估 P/E `{fund.get('pe_forward')}`
* **獲利與成長**：毛利率 `{fund.get('gross_margin_pct')}%` | 營收成長率 `{fund.get('revenue_growth_pct')}%`
* **市場放空比率**：Float 空單佔比 `{fund.get('short_percent_of_float')}%`
* **華爾街平均目標價**：`${fund.get('analyst_target_price')}` | 機構評級: `{fund.get('recommendation_key')}`
"""

        report += f"""
---

### 👨‍💼【操盤室結論速記】
> {decision.get('ai_institutional_summary', '')}
"""
        return report.strip()
