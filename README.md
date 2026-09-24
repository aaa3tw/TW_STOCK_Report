# 📈 台股盤前法人級全維度決策報表系統
### (Taiwan Stock Pre-Market Institutional Report & Decision Engine)

[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Automated%20Workflow-blue?logo=github-actions)](https://github.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen?logo=python)](https://python.org)
[![Gemini 3.8 Flash](https://img.shields.io/badge/AI-Gemini%203.8%20Flash-orange?logo=google-gemini)](https://ai.google.dev/)
[![Discord Webhook](https://img.shields.io/badge/Push-Discord%20Webhook-5865F2?logo=discord)](https://discord.com)

本專案是一個**零伺服器成本、自動化定時執行**的台股盤前法人級情報分析系統。  
每天在**台股開盤前（台灣時間 08:15 AM / UTC 00:15）**由 GitHub Actions 自動喚醒，整合 **yfinance**、**FinMind API**、**台灣證券交易所/櫃買中心官方 Open Data** 與 **Google Gemini 3.8 Flash**，對觀察清單進行全維度量化診斷，並將法人等級的診斷卡片推播至您的 **Discord Webhook**。

---

## 🎯 核心特色與產出內容

### 1. 直擊交易痛點：三大核心決策指引
對觀察清單上的每檔個股，不說模稜兩可的廢話，直接給予操盤室級別的解答：
* 📌 **現在是不是買入時機？原因為何？**（一針見血定調多空動能與風險性）
* 📌 **若不是，什麼條件達成才能買？**（具體條列技術位階、法人籌碼、隔日沖消化之觸發條件）
* 📌 **法人操盤策略**：
  * **建議進場區間**（如回測 5MA / 月線支撐）
  * **建議部位配置**（試單 15% / 突破加碼至 30%）
  * **停利目標價**（第一目標 / 波段壓力）
  * **嚴格停損價**（明確防守點，破位即刻離場）

### 2. 法人高階風控雷達（涵蓋冷門但致命的關鍵指標）
* 🚦 **燈號評級**：🟢 買入（強勢攻勢） / 🟡 觀望等待（區間整理） / 🔴 賣出避開（空方警戒）
* 🛡️ **可轉換公司債 (CB) 轉換價與套利賣壓**：計算平價 (Parity) 與溢價率，精準標記價內放空套利拋售賣壓。
* 🏦 **董監事持股質押比率與內部人動態**：全市場上市公司與上櫃公司董監設質資料庫，警示質押 > 30%~50% 斷頭追繳風險。
* 🔍 **「真假營收」陷阱檢測**：深度比對最新季度存貨週轉天數 (DIO) 與應收帳款週轉天數 (DSO)，防範營收高成長但未能收現或存貨塞在通路端的虛假繁榮。
* 📉 **借券賣出餘額 (SBL，非一般融券)**：追蹤外資法人實質借券放空與避險籌碼，識別法人重兵壓境或空單大幅回補的潛在軋空機會。
* ⚡ **隔日沖分點進駐與當沖比**：監控凱基台北、虎尾幫、美林、富邦建國等隔日沖券商買盤，結合當沖比率（>40%~55%）防範開高走低出貨倒貨陷阱。
* 🤝 **同業與族群連動**：比對同產業指標股漲跌，判定個股屬於「族群領頭羊」、「落後補漲」或「弱勢掉隊」。

### 3. 精緻 Discord Rich Embed 排版
* 🌅 **大盤總覽卡片**：加權指數、櫃買指數、台指期夜盤、費城半導體、美股關鍵連動（NVDA, MU, TSM 等）。
* 🎯 **個股獨立診斷卡**：支援燈號色帶（🟢 綠 / 🟡 黃 / 🔴 紅）、字數上限防截斷機制與批次推播。

---

## 📋 預設觀察清單 (Watchlist)

包含台股精選指標股與美股連動標的（可於 `config/stocks.yaml` 自由調整）：

| 股票代號 | 名稱 | 市場 | 產業別 | 關注亮點 / 美股連動 |
| :--- | :--- | :--- | :--- | :--- |
| **2330.TW** | 台積電 | TWSE | 半導體晶圓製造 | 全球龍頭、TSM ADR 盤前溢價連動 |
| **1785.TWO** | 光洋科 | TPEx | 貴金屬與靶材 | 半導體材料、循環經濟 |
| **2347.TW** | 聯強 | TWSE | 3C供應鏈通路 | 存貨週轉天數與應收帳款品質觀察 |
| **2454.TW** | 聯發科 | TWSE | IC設計 | AI ASIC、邊緣運算、天璣晶片 |
| **3443.TW** | 創意 | TWSE | ASIC與矽智財 | 台積電概念、高價千金股、籌碼集中 |
| **6669.TW** | 緯穎 | TWSE | AI伺服器代工 | CSP 大客戶雲端資本支出、NVDA 連動 |
| **6789.TW** | 采鈺 | TWSE | CIS晶圓級封測 | 影像感測、光學元件 |
| **8088.TWO** | 品安 | TPEx | 記憶體模組與封裝 | 記憶體報價週期、美光 (MU) 連動 |
| **3042.TW** | 晶技 | TWSE | 石英元件 | 頻率控制元件龍頭、車用與AI伺服器 |
| **4551.TW** | 智伸科 | TWSE | 汽車/醫療精密零組件 | 雙引擎動能、營運復甦 |

* 隔夜美股市場觀測：`MU (美光)`, `NVDA (輝達)`, `TSM (台積ADR)`, `WDC/SNDK (威騰/SanDisk)`, `SPCX`

---

## 🚀 快速開始與部署教學 (GitHub Actions)

只需 3 步驟即可完成零伺服器建置：

### 第一步：建立 GitHub Repository
將本專案代碼推送到您的 GitHub 儲存庫：
```bash
git init
git add .
git commit -m "feat: initial commit for taiwan-stock-premarket-reporter"
git branch -M main
git remote add origin https://github.com/<您的用戶名>/<您的儲存庫名>.git
git push -u origin main
```

### 第二步：設定 GitHub Secrets
在您的 GitHub 儲存庫中，前往 **Settings** ➔ **Secrets and variables** ➔ **Actions**，點擊 **New repository secret**，添加以下變數：

1. `GEMINI_API_KEY` (**必填**)：
   * 前往 [Google AI Studio](https://aistudio.google.com/) 免費取得 API Key。
2. `DISCORD_WEBHOOK_URL` (**必填**)：
   * 在您的 Discord 伺服器文字頻道中點選：`頻道設定` ➔ `整合` ➔ `建立 Webhook` ➔ `複製 Webhook 網址`。
3. `FINMIND_API_TOKEN` (**強烈建議**)：
   * 前往 [FinMind 官網](https://finmindtrade.com/) 免費註冊帳號並複製 Token（每小時 300~600 次請求配額）。

### 第三步：啟用與測試 GitHub Actions
1. 前往儲存庫的 **Actions** 分頁。
2. 在左側清單選擇 **「台股盤前法人決策情報報表 (Pre-Market Stock Report)」**。
3. 點擊右上角 **Run workflow** ➔ 勾選 `略過台股交易日檢查` 進行初次即時手動測試。
4. 幾分鐘後，您的 Discord 頻道即可收到精美的盤前戰情報導！

> 💡 **自動排程時間**：已預設於每個台股交易日（週一至週五）台灣時間 **08:15 AM** 自動執行。非交易日（週末與國定假日）將自動跳過不推播。

---

## 💻 本地端開發與測試

若您想在自己的電腦上先行測試：

1. **安裝依賴套件**：
   ```bash
   pip install -r requirements.txt
   ```

2. **建立環境變數檔**：
   複製 `.env.example` 為 `.env` 並填入您的金鑰：
   ```env
   GEMINI_API_KEY=AIzaSy...
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   FINMIND_API_TOKEN=...
   ```

3. **執行乾跑測試 (Dry Run，不發送 Discord，直接在終端機預覽)**：
   ```bash
   python src/main.py --dry-run --skip-calendar-check
   ```

4. **指定自訂股票測試**：
   ```bash
   python src/main.py --custom-stocks 2330,2454,6669 --dry-run --skip-calendar-check
   ```

---

## 📂 專案檔案結構

```
taiwan-stock-premarket-reporter/
├── .github/
│   └── workflows/
│       └── pre_market_report.yml       # GitHub Actions 盤前自動排程
├── config/
│   ├── config.yaml                     # 風控閾值 (質押率/當沖比/DIO/DSO) 與知名隔日沖清單
│   └── stocks.yaml                     # 觀察名單 (台股10檔 + 美股觀測 + 指數)
├── src/
│   ├── main.py                         # 系統主程序入口
│   ├── data/
│   │   ├── market_data.py              # yfinance 行情、MA、KD、MACD、RSI 技術計算
│   │   ├── finmind_client.py           # FinMind 三大法人、SBL借券賣出、當沖比、財報 DIO/DSO
│   │   ├── twse_client.py              # TWSE/TPEx 官方 Open Data 董監質押與可轉債 CB
│   │   └── collector.py                # 多源資料匯流與整合物件
│   ├── analysis/
│   │   └── peer.py                     # 同業族群強弱連動比對
│   ├── ai/
│   │   ├── prompt_builder.py           # 法人級 Prompt 構建器 (強制規範三大決策問題)
│   │   └── gemini_analyzer.py          # Gemini 3.8 Flash 推理與量化備援引擎
│   ├── notifier/
│   │   └── discord.py                  # Discord Webhook Rich Embed 產生與推播
│   └── utils/
│       └── calendar.py                 # 台股交易日判斷
├── requirements.txt                    # 依賴套件
├── .env.example                        # 環境變數範例
└── README.md                           # 完整說明文件
```

---

## ⚖️ 免責聲明 (Disclaimer)

本專案所提供之所有數據分析、AI 推論與操作建議，僅供學術研究、程式化交易邏輯探討與投資輔助參考，**不構成任何形式的金融投資招攬、證券投資諮詢或買賣邀約**。金融市場瞬息萬變，投資必定有風險，使用者應獨立審慎評估並自負投資盈虧。
