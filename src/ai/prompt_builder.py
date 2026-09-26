"""
法人級決策 Prompt 構建模組 (Institutional Prompt Builder)
嚴格要求回答三大核心買賣決策問題與多維度深度風控
"""
from typing import Dict, Any
import json

def build_stock_analysis_prompt(stock_profile: Dict[str, Any], market_context: Dict[str, Any]) -> str:
    """構建傳送給 Gemini 的法人級深度分析 Prompt"""

    stock_json = json.dumps(stock_profile, ensure_ascii=False, indent=2)
    market_json = json.dumps(market_context, ensure_ascii=False, indent=2)

    prompt = f"""
你是一位兼具 20 年實戰經驗的「頂級外資投信首席操盤手兼量化風控長 (Chief Portfolio Manager & CRO)」。
請根據下方提供的盤前客觀多維度數據，為投資人產出【法人等級】的深度盤前決策報告。

【總體市場與外圍背景數據】:
{market_json}

【個股全維度量化診斷數據】:
{stock_json}

---------------------------------------------------------
【分析指引與決策規則】:
1. 綜合審視五大支柱：基本面、籌碼面、技術面、風控雷達（可轉債 CB 套利賣壓、董監質押率、真假營收 DIO/DSO、借券賣出餘額 SBL、當沖比與隔日沖主力）、產業催化劑與同業動態。
2. 燈號判定準則：
   - 🟢 GREEN (買入/多方主攻)：技術多頭排列或低檔剛轉強、外資/投信同步買超、無真假營收與高質押/CB套利賣壓、同業領頭羊。
   - 🟡 YELLOW (觀望等待/震盪整理)：多空訊號拉鋸、即將面臨上方均線壓力、當沖比過高、或需等待回測支撐不破之確認訊號。
   - 🔴 RED (避開/空方警戒/減碼)：均線破位空頭、借券賣出暴增、真假營收異常 (DSO/DIO大幅飆升)、董監質押 > 30%~50%、CB 價內套利放空賣壓沉重。
3. 務必針對以下三個核心問題給出犀利、具體、可執行的決策答案：
   - 問題一：現在是不是買入時機？原因為何？
   - 問題二：若不是，什麼條件達成才能買？(列出具體技術/籌碼/價位觸發條件)
   - 問題三：買入策略 (進場區間、建倉部位 %、停損點位、停利目標價)
4. 點位數值規範：所有策略點位 (進場區間、停損價位、停利目標價) 必須根據個股真實行情給出具體有效數值 (例如 '158 ~ 162 元')，嚴禁輸出 'nan'、'null'、'未知' 或未定義文字。

---------------------------------------------------------
【輸出格式規範】:
請嚴格輸出符合以下結構的 JSON 物件（不得包含任何額外 Markdown 註解或多餘文字）：

{{
  "traffic_light": "GREEN", 
  "action_verdict": "一針見血的操作總結 (例如：回測月線有守，順勢偏多建立試單部位)",
  "three_core_questions": {{
    "is_buy_time": true,
    "buy_reason": "詳細陳述為什麼是 (或不是) 買入時機的核心邏輯",
    "trigger_conditions_to_buy": [
      "若不是買入時機，必須達成的條件1 (如：帶量長紅突破 20MA 壓力位)",
      "必須達成的條件2 (如：外資借券賣出連續 2 日回補逾千張)"
    ],
    "buy_strategy": {{
      "entry_price_range": "建議進場價位區間 (例如：980 ~ 988 元)",
      "position_size_pct": "建議配置資金部位 (例如：初次試單 15%，突破壓力加碼至 25%)",
      "take_profit_target": "停利目標價 (例如：第一目標 1,050 元，波段目標 1,120 元)",
      "stop_loss_price": "明確停損點 (例如：跌破前波支撐 960 元或收盤跌破月線 3%)",
      "execution_notes": "盤中操作提醒 (例如：早盤若跳空 >2% 勿追高，等待 09:30 後拉回沈澱洗盤)"
    }}
  }},
  "deep_dimensions": {{
    "catalyst_analysis": "近期產業催化劑、法說會、新訂單或政策利多分析",
    "cb_arbitrage_assessment": "可轉換公司債 (CB) 轉換價差距、溢價率與放空套利賣壓評估",
    "governance_and_pledge": "董監事持股質押比率與內部人持股安全度評估 (是否有追繳斷頭風險)",
    "revenue_trap_check": "真假營收體檢：存貨週轉天數 (DIO) 與應收帳款天數 (DSO) 異動與塞貨風險",
    "sbl_short_and_chips": "借券賣出餘額 (SBL，非一般融券) 法人實質放空/避險動向與外資投信籌碼解析",
    "day_trading_and_flippers": "當沖比率與隔日沖主力券商開高走低出貨賣壓防範",
    "peer_and_sector": "同業指標股強弱對比與族群資金輪動定位"
  }},
  "ai_institutional_summary": "外資操盤手給操盤室的兩句話晨會結論"
}}
"""
    return prompt.strip()
