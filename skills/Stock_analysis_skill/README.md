# Stock_analysis_skill: 全維度法人級台美股分析技能

一個專為 AI Agent 與 LLM 設計的高階股票量化分析技能，支援台股（上市/上櫃）與美股（個股/ETF/ADR）。

## 核心特性
- **智慧代號識別**：輸入 `2330`、`1785.TWO`、`NVDA`、`TSM` 自動判斷市場與交易幣別。
- **全維度指標矩陣**：均線 (MA5/10/20/60)、KD、MACD、RSI、20日關鍵高低點支撐壓力、量價比。
- **法人高階風控（台股）**：三大法人買賣動向、SBL 借券賣出趨勢、當沖比率警示、可轉債 (CB) 平價與套利賣壓、董監質押率斷頭風險、DIO/DSO「真假營收」陷阱檢測。
- **基本面與估值（美股）**：Trailing/Forward P/E、毛利率、營收成長率、公開市場做空比率、華爾街目標價與評級。
- **核心三大操盤決策**：
  1. 現在是不是買入時機？
  2. 若不是，什麼條件達成才能買？
  3. 操盤買入策略（進場點、停損點、停利點、建議部位成數）。
- **雙輸出格式**：支援格式化 Markdown 報告與標準結構化 JSON。

## 使用範例

```bash
# 輸出 Markdown 報告
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol 2330.TW

# 輸出結構化 JSON
python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol NVDA --format json
```

詳細說明請參閱 [SKILL.md](./SKILL.md)。
