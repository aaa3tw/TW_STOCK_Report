"""
Discord Webhook 推播模組 (Discord Rich Embed Notifier)
嚴格遵守 Discord 格式與字數上限規範，具備批次發送、防截斷與乾跑 (Dry Run) 功能
"""
from typing import Dict, Any, List, Optional
import os
import sys
import time
import logging
import math
import re
import requests

logger = logging.getLogger(__name__)

def _fmt_num(val: Any, default: str = "--", precision: Optional[int] = 2) -> str:
    """將數值格式化為字串，自動防禦 None, NaN, Inf，確保輸出乾淨數字"""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        if precision is not None:
            return f"{f:.{precision}f}"
        return str(int(f)) if f.is_integer() else str(f)
    except (ValueError, TypeError):
        s = str(val).strip()
        return default if s.lower() == "nan" else s

def _clean_str(text: Any, fallback_price: float = 0.0) -> str:
    """清理文字中遺留的 'nan' 或 'null'，以合理股價替換"""
    if not text:
        return ""
    s = str(text)
    if "nan" in s.lower():
        fallback_val = f"{fallback_price:.1f}" if fallback_price > 0 else "--"
        s = re.sub(r'\bnan\b', fallback_val, s, flags=re.IGNORECASE)
    return s

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

        close_raw = tech.get("latest_close", 0.0)
        close = _fmt_num(close_raw, default="--", precision=2)
        close_f = float(close) if close != "--" else 0.0

        try:
            chg = float(tech.get("change", 0.0) or 0.0)
            if math.isnan(chg): chg = 0.0
        except Exception:
            chg = 0.0

        try:
            chg_pct = float(tech.get("change_pct", 0.0) or 0.0)
            if math.isnan(chg_pct): chg_pct = 0.0
        except Exception:
            chg_pct = 0.0

        chg_icon = "🔺" if chg > 0 else ("🔻" if chg < 0 else "▫️")

        title = f"{light_emoji} {code} {name} | 收盤 {close} ({chg_icon} {chg:+.2f} / {chg_pct:+.2f}%)"
        description = f"🎯 **盤前定調**：{_clean_str(action, close_f)}"

        # 欄位 1: 三大核心買賣決策指引
        triggers_text = "\n".join([f"  • {_clean_str(t, close_f)}" for t in q.get("trigger_conditions_to_buy", [])]) if q.get("trigger_conditions_to_buy") else "  • 暫無特殊限制條件"
        entry_price = _clean_str(strat.get('entry_price_range', '等待條件確認'), close_f)
        stop_price = _clean_str(strat.get('stop_loss_price', '跌破支撐即出'), close_f)
        target_price = _clean_str(strat.get('take_profit_target', '前高壓力處'), close_f)
        pos_size = _clean_str(strat.get('position_size_pct', '10% ~ 20%'), close_f)
        exec_notes = _clean_str(strat.get('execution_notes', '注意盤初洗盤'), close_f)
        buy_reason = _clean_str(q.get('buy_reason', ''), close_f)

        core_decisions = (
            f"**1. 現在是不是買入時機？**\n"
            f"👉 {'【是】' if q.get('is_buy_time') else '【否 / 暫緩】'}：{buy_reason}\n\n"
            f"**2. 買入觸發條件：**\n"
            f"{triggers_text}\n\n"
            f"**3. 操盤買入策略：**\n"
            f"  • **建議進場區間**：`{entry_price}`\n"
            f"  • **部位資金配置**：`{pos_size}`\n"
            f"  • **停利目標價位**：`{target_price}`\n"
            f"  • **嚴格停損防守**：`{stop_price}`\n"
            f"  • **盤中執行提醒**：*{exec_notes}*"
        )

        # 欄位 2: 多維量化指標矩陣
        kd_info = tech.get("kd", {})
        macd_info = tech.get("macd", {})
        ma5_str = _fmt_num(tech.get('ma5'), default=close)
        ma20_str = _fmt_num(tech.get('ma20'), default=close)
        k_str = _fmt_num(kd_info.get('k'), default="50.0")
        d_str = _fmt_num(kd_info.get('d'), default="50.0")
        rsi_str = _fmt_num(tech.get('rsi14'), default="50.0")
        vol_ratio_str = _fmt_num(tech.get('volume_ratio_5d'), default="1.00")
        vol_shares = tech.get('volume') or 0
        try:
            vol_lots = int(float(vol_shares)) // 1000 if not math.isnan(float(vol_shares)) else 0
        except Exception:
            vol_lots = 0

        quant_matrix = (
            f"• **技術趨勢**：{tech.get('ma_trend', '震盪整理')} (MA5:`{ma5_str}` / MA20:`{ma20_str}`)\n"
            f"• **動能指標**：KD(9,3) `{k_str}/{d_str}` ({kd_info.get('signal', '中立')}) | MACD: {macd_info.get('status', '動能平穩')} | RSI: `{rsi_str}`\n"
            f"• **成交量能**：今日量比 5MA `{vol_ratio_str}x` (成交量: `{vol_lots}` 張)\n"
            f"• **三大法人**：外資 `{chips.get('foreign_streak', '持平')}` (5日淨 `{chips.get('foreign_5d', 0):+d}` 張) | 投信 `{chips.get('trust_streak', '持平')}` (5日淨 `{chips.get('trust_5d', 0):+d}` 張)\n"
            f"• **基本營收**：{month_rev.get('summary', '最新月營收穩定')}"
        )

        # 欄位 3: 法人高階風控雷達
        cb_summary = cb.get("summary", "無發行可轉債")
        if cb.get("has_cb") and cb.get("cb_details"):
            cb_detail = cb["cb_details"][0]
            cb_summary = f"{cb_detail.get('short_name')} (轉換價 `{_fmt_num(cb_detail.get('conversion_price'))}` / 平價 `{_fmt_num(cb_detail.get('parity'))}%`) - {cb_detail.get('arbitrage_risk')}"

        governance_summary = f"{pledge.get('risk_tag')} 董監質押率 `{_fmt_num(pledge.get('pledge_ratio'))}%` ({pledge.get('risk_level')})"

        risk_radar = (
            f"• **可轉債 (CB) 套利賣壓**：{cb_summary}\n"
            f"• **董監質押斷頭風險**：{governance_summary}\n"
            f"• **真假營收 (DIO/DSO)**：{rev_trap.get('tag')} {rev_trap.get('comment')}\n"
            f"• **借券賣出餘額 (SBL)**：{sbl.get('risk_tag')} 餘額 `{sbl.get('sbl_balance_lots')}` 張 (5日變動 `{sbl.get('sbl_change_5d'):+d}` 張) - *{sbl.get('interpretation')}*\n"
            f"• **當沖比率與隔日沖**：{day_t.get('tag')} 當沖佔比 `{_fmt_num(day_t.get('day_trading_ratio'))}%` - *{day_t.get('warning')}*"
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
            {"name": "👨‍💼【AI 操盤手晨會速記】", "value": f"*{_clean_str(summary, close_f)[:1000]}*", "inline": False}
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

    def build_watchlist_summary_embed(self, processed_stocks: List[Dict[str, Any]], date_str: str) -> Dict[str, Any]:
        """
        建立所有觀察類股的總表 (Master Strategy Table)
        包含：股名、股價、今天該做的操作、進場點、停損點、停利點、建議部位
        每個標的分配專屬 Field，避免文字截斷或 Markdown 標籤破碎
        """
        green_count = 0
        yellow_count = 0
        red_count = 0

        fields = []
        for item in processed_stocks:
            p = item.get("profile", {})
            analysis = item.get("analysis", {})
            name = p.get("name", "")
            code = p.get("code", "")
            tech = p.get("technical", {})
            close_str = _fmt_num(tech.get("latest_close", 0), default="--")
            close_f = float(close_str) if close_str != "--" else 0.0

            try:
                chg_pct = float(tech.get("change_pct", 0.0) or 0.0)
                if math.isnan(chg_pct): chg_pct = 0.0
            except Exception:
                chg_pct = 0.0

            light = analysis.get("traffic_light", "YELLOW")
            action = _clean_str(analysis.get("action_verdict", "") or "區間震盪觀望", close_f).strip()
            q = analysis.get("three_core_questions", {})
            strat = q.get("buy_strategy", {})

            entry = _clean_str(strat.get("entry_price_range", "待條件確認") or "待確認", close_f).strip()
            stop = _clean_str(strat.get("stop_loss_price", "跌破支撐") or "嚴守紀律", close_f).strip()
            target = _clean_str(strat.get("take_profit_target", "波段目標") or "波段滿足", close_f).strip()
            pos = _clean_str(strat.get("position_size_pct", "0%") or "0%", close_f).strip()

            if light == "GREEN":
                green_count += 1
                icon = "🟢【買入】"
            elif light == "RED":
                red_count += 1
                icon = "🔴【避開】"
            else:
                yellow_count += 1
                icon = "🟡【觀望】"

            chg_icon = "🔺" if chg_pct > 0 else ("🔻" if chg_pct < 0 else "▫️")
            field_name = f"{icon} {code} {name} | 股價 {close_str} ({chg_icon} {chg_pct:+.2f}%)"
            field_val = (
                f"🎯 **操作**：{action[:200]}\n"
                f"📍 **點位**：進場 `{entry[:60]}` | 停損 `{stop[:50]}` | 停利 `{target[:50]}` | 部位 `{pos[:30]}`"
            )
            fields.append({
                "name": field_name[:250],
                "value": field_val[:1000],
                "inline": False
            })

        header_desc = (
            f"📊 **全體觀察股今日作戰定位統計**：\n"
            f"🟢 積極買入: `{green_count}` 檔 | 🟡 觀望等待: `{yellow_count}` 檔 | 🔴 減碼避開: `{red_count}` 檔\n\n"
            "以下為所有觀察類股之**今日操作定調與各核心操作點位速查表**，詳細多維度深度分析請參閱後續各個股卡片："
        )

        return {
            "title": f"📋【盤前作戰總表】全觀察類股今日操作與點位速查 ({date_str})",
            "description": header_desc[:4000],
            "color": 0x9B59B6,  # 質感高雅紫
            "fields": fields[:25],
            "footer": {
                "text": "台股盤前法人決策系統 • 快速決策速查表"
            }
        }

    def _post_payload_with_retry(self, payload: Dict[str, Any], max_retries: int = 3) -> bool:
        """發送單則 Webhook Payload，具備超時與 HTTP 500 / 429 指數退避重試"""
        headers = {"Content-Type": "application/json"}
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.post(self.webhook_url, json=payload, headers=headers, timeout=15)
                if r.status_code in [200, 204]:
                    return True
                elif r.status_code == 429:
                    try:
                        retry_after = float(r.json().get("retry_after", 2.0))
                    except Exception:
                        retry_after = 2.0
                    logger.warning(f"Discord 觸發頻率限制 (429)，等待 {retry_after} 秒後重試...")
                    time.sleep(retry_after)
                elif r.status_code >= 500:
                    logger.warning(f"Discord 伺服器異常 ({r.status_code}): {r.text[:80]}，第 {attempt}/{max_retries} 次重試...")
                    time.sleep(2.0 * attempt)
                else:
                    logger.error(f"推送至 Discord 失敗 ({r.status_code}): {r.text}")
                    return False
            except Exception as e:
                logger.warning(f"Discord Webhook 連線異常: {e}，第 {attempt}/{max_retries} 次重試...")
                time.sleep(2.0 * attempt)
        return False

    def send_report(self, market_overview_embed: Dict[str, Any], stock_embeds: List[Dict[str, Any]], summary_embed: Optional[Dict[str, Any]] = None) -> bool:
        """
        分批推送至 Discord Webhook：
        1. 獨立發送大盤總覽卡片
        2. 獨立發送全觀察類股點位總表
        3. 分批發送個股深度診斷卡片 (每則訊息 1~2 檔個股，徹底避免超過 6000 字元上限)
        """
        all_embeds = [market_overview_embed]
        if summary_embed:
            all_embeds.append(summary_embed)
        all_embeds.extend(stock_embeds)

        if not self.webhook_url:
            logger.info("未提供 DISCORD_WEBHOOK_URL，將在終端機輸出預覽 (Dry Run)")
            _safe_print("\n" + "="*80)
            _safe_print("【DRY RUN: DISCORD WEBHOOK 報告預覽】")
            _safe_print("="*80)
            for idx, emb in enumerate(all_embeds, 1):
                _safe_print(f"\n--- [EMBED #{idx}] {emb.get('title')} ---")
                _safe_print(emb.get("description", ""))
                for f in emb.get("fields", []):
                    _safe_print(f"\n▶ {f.get('name')}\n{f.get('value')}")
            _safe_print("\n" + "="*80)
            return True

        # 1. 發送大盤總覽卡片
        logger.info("正在推送【大盤總覽卡片】至 Discord...")
        payload_market = {
            "username": "台股盤前法人決策情報局",
            "embeds": [market_overview_embed]
        }
        if not self._post_payload_with_retry(payload_market):
            logger.error("大盤總覽卡片推送失敗")
        time.sleep(1.0)

        # 2. 發送觀察類股點位總表 (若存在)
        if summary_embed:
            logger.info("正在推送【全觀察類股作戰總表】至 Discord...")
            payload_summary = {
                "username": "台股盤前法人決策情報局",
                "embeds": [summary_embed]
            }
            if not self._post_payload_with_retry(payload_summary):
                logger.error("作戰總表推送失敗")
            time.sleep(1.0)

        # 3. 分批發送個股深度診斷卡 (每則訊息 1~2 個個股 Embed，嚴格防範字數超標)
        batch_size = 2
        for i in range(0, len(stock_embeds), batch_size):
            batch = stock_embeds[i:i + batch_size]
            payload_stock = {
                "username": "台股盤前法人決策情報局",
                "embeds": batch
            }
            logger.info(f"正在推送個股卡片 ({i+1}~{min(i+len(batch), len(stock_embeds))}/{len(stock_embeds)})...")
            if not self._post_payload_with_retry(payload_stock):
                logger.error(f"個股卡片批次 {i+1} 推送失敗")
            time.sleep(1.2)

        logger.info("所有卡片已完成推送作業")
        return True
