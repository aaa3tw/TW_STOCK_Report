"""
台股盤前法人級全維度決策報表 - 主程式 (Main Entrypoint)
支援定時排程、自訂股票觀察名單、乾跑預覽與完整日誌
"""
import os
import sys
import argparse
import logging
from typing import Dict, Any, List
import yaml

# 加入專案路徑
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.calendar import is_taiwan_trading_day, get_current_tw_date, get_current_tw_time
from src.data.collector import DataCollector
from src.ai.gemini_analyzer import GeminiStockAnalyzer
from src.notifier.discord import DiscordNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PremarketReporter")

def load_yaml(file_path: str) -> Dict[str, Any]:
    """載入 YAML 設定檔"""
    if not os.path.exists(file_path):
        logger.error(f"找不到設定檔案: {file_path}")
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    parser = argparse.ArgumentParser(description="台股盤前法人級決策報表系統")
    parser.add_argument("--config", default="config/config.yaml", help="系統參數設定檔路徑")
    parser.add_argument("--stocks", default="config/stocks.yaml", help="觀察清單設定檔路徑")
    parser.add_argument("--custom-stocks", type=str, default="", help="覆蓋觀察清單 (逗號分隔代號，如 2330,2454)")
    parser.add_argument("--dry-run", action="store_true", help="乾跑模式，僅在終端機輸出預覽")
    parser.add_argument("--skip-calendar-check", action="store_true", help="強制執行，略過週末/休市日檢查")
    parser.add_argument("--debug", action="store_true", help="開啟 Debug 詳細除錯日誌")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("==================================================")
    logger.info("🚀 啟動台股盤前法人級全維度決策報表系統")
    logger.info(f"當前台灣時間: {get_current_tw_time()}")
    logger.info("==================================================")

    # 1. 交易日檢查
    if not args.skip_calendar_check and not is_taiwan_trading_day():
        logger.info("今日非台股交易日 (週末或國定休市日)，排程略過執行。")
        sys.exit(0)

    # 2. 載入配置
    config = load_yaml(args.config)
    stocks_cfg = load_yaml(args.stocks)

    tw_date = get_current_tw_date()

    # 3. 初始化模組
    finmind_token = os.environ.get("FINMIND_API_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    webhook_url = "" if args.dry_run else os.environ.get("DISCORD_WEBHOOK_URL", "")

    collector = DataCollector(finmind_token=finmind_token)
    analyzer = GeminiStockAnalyzer(api_key=gemini_key)
    notifier = DiscordNotifier(webhook_url=webhook_url)

    # 4. 取得大盤總覽
    logger.info("1/3 正在擷取國際大盤指數與隔夜美股關鍵行情...")
    market_overview = collector.collect_market_overview(stocks_cfg)
    market_embed = notifier.build_market_overview_embed(market_overview, tw_date)

    # 5. 處理個股觀察清單
    taiwan_stocks = stocks_cfg.get("taiwan_stocks", [])

    # 若有傳入 custom_stocks 參數，進行過濾或動態加入
    if args.custom_stocks:
        custom_codes = [c.strip().upper() for c in args.custom_stocks.split(",") if c.strip()]
        logger.info(f"使用自訂觀察股票清單: {custom_codes}")
        filtered_stocks = []
        for c in custom_codes:
            # 尋找是否在原本配置中
            matched = next((s for s in taiwan_stocks if s.get("code") == c or c in s.get("symbol", "")), None)
            if matched:
                filtered_stocks.append(matched)
            else:
                # 動態補建基本配置
                market_type = "TPEx" if c.startswith(("17", "80", "52", "64", "65", "83")) else "TWSE"
                suffix = ".TWO" if market_type == "TPEx" else ".TW"
                filtered_stocks.append({
                    "symbol": f"{c}{suffix}",
                    "code": c,
                    "name": c,
                    "market": market_type,
                    "sector": "一般電子/傳產",
                    "peers": []
                })
        taiwan_stocks = filtered_stocks

    total_stocks = len(taiwan_stocks)
    logger.info(f"2/3 開始分析觀察清單股票，共 {total_stocks} 檔...")

    stock_embeds: List[Dict[str, Any]] = []

    for idx, s_cfg in enumerate(taiwan_stocks, 1):
        name = s_cfg.get("name", s_cfg.get("code"))
        sym = s_cfg.get("symbol")
        logger.info(f"[{idx}/{total_stocks}] 分析中: {name} ({sym})")

        try:
            # 數據收集
            profile = collector.collect_stock_full_profile(s_cfg)
            if not profile:
                logger.warning(f"跳過 {name}，無法取得完整資料")
                continue

            # AI 法人診斷
            analysis_result = analyzer.analyze_stock(profile, market_overview)

            # 建立 Discord 卡片
            embed = notifier.build_stock_card_embed(profile, analysis_result, tw_date)
            stock_embeds.append(embed)

        except Exception as e:
            logger.error(f"分析股票 {name} 時發生未預期異常: {e}", exc_info=True)

    # 6. 推送至 Discord Webhook
    logger.info(f"3/3 準備推播報表 (大盤卡片 1 張 + 個股卡片 {len(stock_embeds)} 張)...")
    success = notifier.send_report(market_embed, stock_embeds)

    if success:
        logger.info("🎉 盤前報表推播作業圓滿完成！")
    else:
        logger.error("⚠️ 推播作業發生部分錯誤，請檢查 Discord Webhook 設定與日誌。")

if __name__ == "__main__":
    main()
