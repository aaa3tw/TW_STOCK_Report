---
name: Stock_analysis_skill
description: |
  全維度法人級台美股即時診斷與量化操盤分析 Skill。
  支援輸入任一台股（如 2330, 2330.TW, 1785.TWO, 4551）或美股（如 NVDA, TSM, MU, AAPL, SPY）代號，自動聚合多維度真實數據並產出操盤指引：
  1. 技術面與動能矩陣：MA5/10/20/60 多空排列、KD(9,3,3) 交叉與鈍化、MACD 柱狀體收斂擴大、RSI(14)、20日關鍵波段支撐/壓力位、今日量比 5MA 係數。
  2. 籌碼與法人動態（台股）：外資/投信連續買賣天數與 5 日淨買賣張數、借券賣出 (SBL) 餘額趨勢與法人避險動態、當沖成交佔比過熱示警。
  3. 法人高階風控雷達（台股）：TPEx 可轉換公司債 (CB) 平價與價內放空套利賣壓、TWSE/TPEx 董監事持股質押比率與追繳斷頭警戒、DIO/DSO「真假營收」塞貨與銷貨未收現陷阱檢測、最新公告月營收成長率。
  4. 美股基本面與華爾街動態（美股）：Trailing/Forward P/E、毛利率、營收成長率、公開市場做空比率 (Short % of Float)、華爾街平均目標價與機構評級。
  5. 核心三大操盤決策問題：
     - 問題一：現在是不是買入時機？原因為何？
     - 問題二：若不是，什麼條件達成才能買？(列出具體觸發條件)
     - 問題三：操盤買入策略 (建議進場區間、部位配置比例、第一停利目標價、嚴格停損防守價、盤中執行提醒)。

  當使用者或對話情境出現以下需求時，LLM 必須使用此 Skill：
  - 「幫我分析 XXXX」、「這檔股票可以買嗎？」、「現在是不是買入時機？」
  - 「分析 2330」、「看聯發科 2454」、「智伸科 4551 操盤點位」
  - 「NVDA 分析」、「TSM 美股評估」、「MU 買進策略」
  - 詢問任何台股或美股之技術指標、法人籌碼、真假營收、可轉債賣壓、董監質押或買賣策略。
---

# 📈 Stock_analysis_skill: 全維度法人級台美股量化分析指南

本 Skill 為大語言模型 (LLM)、自主 Agent 或投資分析系統提供標準化的股票多維度診斷能力。只需輸入任一台股或美股代號，即可自動擷取實時與歷史數據，計算技術指標、籌碼面、風控雷達與基本面，並產出清晰的買賣決策建議。

---

## 🚀 快速調用方式

### 方式一：命令列 (CLI) 調用 (推薦給 Agent / Subagent)

在終端機中執行腳本即可直接取得分析結果：

```bash
# 1. 分析單一股票 (預設輸出 Markdown 格式)
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol 2330.TW

# 2. 分析美股並取得結構化 JSON (適合 LLM / Function Calling 解析)
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol NVDA --format json

# 3. 簡潔代號自動識別 (如純數字台股)
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol 4551

# 4. 批次分析多檔標的 (逗號分隔)
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol "2330.TW,NVDA,4551.TW"

# 5. 輸出儲存為檔案
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol 2330.TW --output report_2330.md
```

### 方式二：Python 程式碼直接引入

```python
from skills.Stock_analysis_skill.scripts.analyzer import StockAnalyzer

analyzer = StockAnalyzer()

# 傳入台股或美股代號
report = analyzer.analyze("2330.TW")

# 取得 Markdown 格式文字報告
print(report["markdown_report"])

# 取得特定量化數值
print(f"收盤價: {report['technical']['latest_close']}")
print(f"操盤燈號: {report['decision']['traffic_light']}")
print(f"進場區間: {report['decision']['three_core_questions']['buy_strategy']['entry_price_range']}")
```

---

## 📥 支援之標的代號輸入規範

系統內建智慧代號解析器 (`resolve_symbol`)，支援以下多種輸入風格：

| 輸入格式範例 | 識別市場 | 說明 |
| :--- | :--- | :--- |
| `2330` | 台股上市 (TWSE) | 自動偵測並補全為 `2330.TW` |
| `1785` 或 `8088` | 台股上櫃 (TPEx) | 自動測試上市/上櫃連線並補全為 `1785.TWO` |
| `2330.TW` | 台股上市 (TWSE) | 明確指定上市市場 |
| `1785.TWO` | 台股上櫃 (TPEx) | 明確指定上櫃市場 |
| `NVDA`, `MU`, `TSM`, `AAPL` | 美股 (US) | 識別為美股，自動取得華爾街預估與做空比率 |
| `SPY`, `QQQ`, `SPCX` | 美股 ETF (US) | 支援 ETF 指標與動能分析 |

---

## 📊 輸出數據結構解析

調用結果返回之結構化 JSON 包含三大核心部分：

```json
{
  "symbol": "2330.TW",
  "code": "2330",
  "market": "TWSE",
  "market_type": "TAIWAN",
  "currency": "TWD",
  "analysis_time": "2026-09-26 19:48:21",
  "technical": {
    "latest_close": 2475.0,
    "change": -25.0,
    "change_pct": -1.0,
    "volume": 13043734,
    "volume_ratio_5d": 0.64,
    "ma5": 2475.0,
    "ma10": 2433.39,
    "ma20": 2427.88,
    "ma60": 2394.79,
    "ma_trend": "站上月線 (多方震盪整理)",
    "kd": { "k": 72.3, "d": 61.65, "signal": "中立" },
    "macd": { "dif": 12.5, "dea": 10.2, "hist": 4.6, "status": "紅柱縮小 (多方動能趨緩)" },
    "rsi14": 60.55,
    "support_level": 2368.03,
    "resistance_level": 2510.0
  },
  "fundamentals": { ... },
  "decision": {
    "traffic_light": "YELLOW",
    "action_verdict": "營收伴隨DIO/DSO雙增警訊，籌碼短線拉鋸，建議於月線附近觀望等待回測不破或指標沉澱後再行介入。",
    "three_core_questions": {
      "is_buy_time": false,
      "buy_reason": "詳細陳述核心邏輯...",
      "trigger_conditions_to_buy": [
        "條件一：帶量突破前高壓力...",
        "條件二：外資與投信轉為連續同步買超..."
      ],
      "buy_strategy": {
        "entry_price_range": "2420 ~ 2435 元",
        "position_size_pct": "初次試單僅限 10%",
        "take_profit_target": "第一目標 2510 元，波段目標 2580 元",
        "stop_loss_price": "收盤跌破季線 2390 元",
        "execution_notes": "盤中若量能未能放大至 5 日均量之上，切勿追價..."
      }
    },
    "deep_dimensions": { ... }
  },
  "markdown_report": "完整的 Markdown 報告字串..."
}
```

---

## 🤖 LLM 回應使用者指引

當其他 LLM 使用此 Skill 取得報告後，應遵循以下原則向終端投資人彙報：

1. **先給定調與燈號**：一開始先明確告知 `🟢 買入`、`🟡 觀望` 或 `🔴 避開`，並附上最新收盤價與當日漲跌。
2. **回答三大核心問題**：
   - 現在能不能買？理由是什麼？
   - 若不能買，需要達成哪些具體條件（如放量站穩月線、法人空單回補）？
   - 具體操盤點位：進場區間、停損價位、停利價位、資金成數。
3. **指出關鍵風險指標**：
   - 台股特別關注：真假營收（DIO/DSO 塞貨天數）、可轉債套利賣壓、董監質押率、當沖比率。
   - 美股特別關注：做空佔比 (Short % of Float)、華爾街目標價、毛利率變化。
4. **數字百分之百精確**：所有價位、均線、法人張數均由量化數據支援，不輸出模糊空泛預測。
