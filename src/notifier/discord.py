"""
Discord Webhook 推播模組 (Discord Rich Embed Notifier)
嚴格遵守 Discord 格式與字數上限規範，具備批次發送、防截斷與乾跑 (Dry Run) 功能
"""
from typing import Dict, Any, List, Optional
import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.colors = {
            "GREEN": 0x2ECC71,    # 🟢 買入 / 強勢
            "YELLOW": 0xF1C40F,   # 🟡 觀望 / 中立
            "RED": 0xE74C3C,      # 🔴 避開 / 空方
            "BLUE": 0x3498DB       # 🌐 大盤總覽
        }

    def build_market_overview_embed(self, market_data: Dict[str, Any], date_str: str) -> Dict[str, Any]:
        """建立大盤與國際市場總覽 Embed"""
        indices = market_data.get("indices", [])
        us_stocks = market_data.get("us_stocks", [])

        idx_lines = []
        for idx in indices:
            icon = "🔺" if idx.get("change", 0) > 0 else ("🔻" if idx.get("change", 0) < 0 else "▫️")
            idx_lines.append(f"{icon} **{idx.get('name')}**: `{idx.get('close')}` ({idx.get('change_pct', 0.0):+.2f}%)")

        us_lines = []
        for us in us_stocks:
            icon = "🔺" if us.get("change", 0) > 0 else ("🔻" if us.get("change", 0) < 0 else "▫️")
            us_lines.append(f"{icon} **{us.get('name')}**: `{us.get('close')}` ({us.get('change_pct', 0.0):+.2f}%) - *{us.get('relevance')}*")

        desc = (
            "晨間台股開盤前國際股市、台指夜盤與美股關鍵權值動向掃描。\n"
            "請留意國際半導體與 AI 供應鏈隔夜表現對台股開盤之連動影響。"
        )

        fields = [
            {
                "name": "🌐 國際與台灣主要指數行情",
                "value": "\n".join(idx_lines) if idx_lines else "暫無指數數據",
                "inline": False
            },
            {
                "name": "🇺🇸 隔夜美股關鍵連動標的",
                "value": "\n".join(us_lines) if us_lines else "暫無美股數據",
                "inline": False
            }
        ]

        return {
            "title": f"🌅【台股盤前戰情報導】大盤與外圍市場總覽 ({date_str})",
            "description": desc,
            "color": self.colors["BLUE"],
            "fields": fields,
            "footer": {
                "text": "台股盤前法人決策系統 • 每日開盤前自動更新"
            }
        }

    def build_stock_card_embed(self, p: Dict[str, Any], analysis: Dict[str, Any], date_str: str) -> Dict[str, Any]:
        """建立個股法人級全維度決策 Embed"""
        name = p.get("name")
        code = p.get("code")
        tech = p.get("technical", {})
        chips = p.get("chips", {})
        sbl = p.get("sbl_short", {})
        day_t = p.get("day_trading", {})
        rev_trap = p.get("revenue_trap", {})
        pledge = p.get("governance_pledge", {})
        cb = p.get("convertible_bond", {})
        peer = p.get("peer_comparison", {})
        month_rev = p.get("monthly_revenue", {})

        light = analysis.get("traffic_light", "YELLOW")
        action = analysis.get("action_verdict", "")
        q = analysis.get("three_core_questions", {})
        strat = q.get("buy_strategy", {})
        deep = analysis.get("deep_dimensions", {})
        summary = analysis.get("ai_institutional_summary", "")

        light_emoji = "🟢【買入建議】" if light == "GREEN" else ("🟡【觀望等待】" if light == "YELLOW" else "🔴【避開警戒】")
        color = self.colors.get(light, self.colors["YELLOW"])

        close = round(float(tech.get("latest_close", 0)), 2)
        chg = round(float(tech.get("change", 0.0)), 2)
        chg_pct = round(float(tech.get("change_pct", 0.0)), 2)
        chg_icon = "🔺" if chg > 0 else ("🔻" if chg < 0 else "▫️")

        title = f"{light_emoji} {code} {name} | 收盤 {close} ({chg_icon} {chg:+.2f} / {chg_pct:+.2f}%)"
        description = f"🎯 **盤前定調**：{action}"

        # 欄位 1: 三大核心買賣決策指引
        triggers_text = "\n".join([f"  • {t}" for t in q.get("trigger_conditions_to_buy", [])]) if q.get("trigger_conditions_to_buy") else "  • 暫無特殊限制條件"
        core_decisions = (
            f"**1. 現在是不是買入時機？**\n"
            f"👉 {'【是】' if q.get('is_buy_time') else '【否 / 暫緩】'}：{q.get('buy_reason')}\n\n"
            f"**2. 買入觸發條件：**\n"
            f"{triggers_text}\n\n"
            f"**3. 操盤買入策略：**\n"
            f"  • **建議進場區間**：`{strat.get('entry_price_range', '等待條件確認')}`\n"
            f"  • **部位資金配置**：`{strat.get('position_size_pct', '10% ~ 20%')}`\n"
            f"  • **停利目標價位**：`{strat.get('take_profit_target', '前高壓力處')}`\n"
            f"  • **嚴格停損防守**：`{strat.get('stop_loss_price', '跌破支撐即出')}`\n"
            f"  • **盤中執行提醒**：*{strat.get('execution_notes', '注意盤初洗盤')}*"
        )

        # 欄位 2: 多維量化指標矩陣
        kd_info = tech.get("kd", {})
        macd_info = tech.get("macd", {})
        quant_matrix = (
            f"• **技術趨勢**：{tech.get('ma_trend')} (MA5:`{tech.get('ma5')}` / MA20:`{tech.get('ma20')}`)\n"
            f"• **動能指標**：KD(9,3) `{kd_info.get('k')}/{kd_info.get('d')}` ({kd_info.get('signal')}) | MACD: {macd_info.get('status')} | RSI: `{tech.get('rsi14')}`\n"
            f"• **成交量能**：今日量比 5MA `{tech.get('volume_ratio_5d')}x` (成交量: `{tech.get('volume') // 1000}` 張)\n"
            f"• **三大法人**：外資 `{chips.get('foreign_streak')}` (5日淨 `{chips.get('foreign_5d'):+d}` 張) | 投信 `{chips.get('trust_streak')}` (5日淨 `{chips.get('trust_5d'):+d}` 張)\n"
            f"• **基本營收**：{month_rev.get('summary', '最新月營收穩定')}"
        )

        # 欄位 3: 法人高階風控雷達
        cb_summary = cb.get("summary", "無發行可轉債")
        if cb.get("has_cb") and cb.get("cb_details"):
            cb_detail = cb["cb_details"][0]
            cb_summary = f"{cb_detail.get('short_name')} (轉換價 `{cb_detail.get('conversion_price')}` / 平價 `{cb_detail.get('parity')}%`) - {cb_detail.get('arbitrage_risk')}"

        governance_summary = f"{pledge.get('risk_tag')} 董監質押率 `{pledge.get('pledge_ratio')}%` ({pledge.get('risk_level')})"

        risk_radar = (
            f"• **可轉債 (CB) 套利賣壓**：{cb_summary}\n"
            f"• **董監質押斷頭風險**：{governance_summary}\n"
            f"• **真假營收 (DIO/DSO)**：{rev_trap.get('tag')} {rev_trap.get('comment')}\n"
            f"• **借券賣出餘額 (SBL)**：{sbl.get('risk_tag')} 餘額 `{sbl.get('sbl_balance_lots')}` 張 (5日變動 `{sbl.get('sbl_change_5d'):+d}` 張) - *{sbl.get('interpretation')}*\n"
            f"• **當沖比率與隔日沖**：{day_t.get('tag')} 當沖佔比 `{day_t.get('day_trading_ratio')}%` - *{day_t.get('warning')}*"
        )

        # 欄位 4: 催化劑與族群同業動態
        catalysts_and_peers = (
            f"• **產業催化劑 (Catalyst)**：{deep.get('catalyst_analysis', '關注產業供需循環與下半年旺季拉貨力道。')}\n"
            f"• **同業族群強弱連動**：{peer.get('tag', '⚪')} {peer.get('role', '')} ({peer.get('comment', '與族群同向連動')})"
        )

        fields = [
            {"name": "🎯【三大核心買賣決策指引】", "value": core_decisions[:1020], "inline": False},
            {"name": "📊【多維量化指標矩陣】", "value": quant_matrix[:1020], "inline": False},
            {"name": "🛡️【法人高階風控雷達】", "value": risk_radar[:1020], "inline": False},
            {"name": "🚀【催化劑與族群同業動態】", "value": catalysts_and_peers[:1020], "inline": False},
            {"name": "👨‍💼【AI 操盤手晨會速記】", "value": f"*{summary[:1000]}*", "inline": False}
        ]

        return {
            "title": title[:256],
            "description": description[:4000],
            "color": color,
            "fields": fields,
            "footer": {
                "text": f"代號: {code} • 產業: {p.get('sector')} • 日期: {date_str}"
            }
        }

    def send_report(self, market_overview_embed: Dict[str, Any], stock_embeds: List[Dict[str, Any]]) -> bool:
        """
        分批推送至 Discord Webhook (每次最多 4 個 Embed 以確保不觸發 6000 字元與 10 Embed 上限)
        """
        all_embeds = [market_overview_embed] + stock_embeds

        if not self.webhook_url:
            logger.info("未提供 DISCORD_WEBHOOK_URL，將在終端機輸出預覽 (Dry Run)")
            print("\n" + "="*80)
            print("【DRY RUN: DISCORD WEBHOOK 報告預覽】")
            print("="*80)
            for idx, emb in enumerate(all_embeds, 1):
                print(f"\n--- [EMBED #{idx}] {emb.get('title')} ---")
                print(emb.get("description", ""))
                for f in emb.get("fields", []):
                    print(f"\n▶ {f.get('name')}\n{f.get('value')}")
            print("\n" + "="*80)
            return True

        # 分批發送 (每批 3 個 Embed，避免 Payload 超標)
        batch_size = 3
        total_sent = 0

        for i in range(0, len(all_embeds), batch_size):
            batch = all_embeds[i:i + batch_size]
            payload = {
                "username": "台股盤前法人決策情報局",
                "avatar_url": "https://img.icons8.com/color/512/bullish.png",
                "embeds": batch
            }

            try:
                r = requests.post(self.webhook_url, json=payload, timeout=15)
                if r.status_code in [200, 204]:
                    logger.info(f"成功推送第 {i+1} ~ {i+len(batch)} 則 Embed 到 Discord")
                    total_sent += len(batch)
                else:
                    logger.error(f"推送至 Discord 失敗 ({r.status_code}): {r.text}")
                    return False
            except Exception as e:
                logger.error(f"推送至 Discord Webhook 發生連線異常: {e}")
                return False

            time.sleep(1.0)  # 避免觸發 Discord 頻率限制

        logger.info(f"所有報告已成功推送至 Discord，共 {total_sent} 個卡片")
        return True
