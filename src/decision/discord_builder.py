"""
TW_STOCK_DECISION - 決策結論與每週勝率 Discord 專屬報告生成器
包含：早盤決策卡、午盤結論對比卡、週六統整勝率卡片
"""
from typing import Dict, Any, List, Optional
import math

class DecisionDiscordBuilder:
    def __init__(self):
        self.colors = {
            "BUY": 0x2ECC71,        # 綠色
            "SELL": 0xE74C3C,       # 紅色
            "HOLD": 0xF1C40F,       # 黃色
            "SUMMARY": 0x3498DB,    # 藍色
            "ACCURACY_HIGH": 0x00FF7F, # 淺綠
            "ACCURACY_MED": 0xF39C12,  # 橘黃
            "ACCURACY_LOW": 0xE74C3C   # 紅色
        }

    def build_morning_decision_embed(self, date_str: str, decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        早上 10:00 - 盤中 AI 即時決策發布卡片
        """
        lines = []
        buy_cnt = 0
        sell_cnt = 0
        hold_cnt = 0

        for item in decisions:
            sym = item.get("symbol", "")
            name = item.get("name", sym)
            price = item.get("price", 0.0)
            chg_pct = item.get("change_pct", 0.0)
            dec = (item.get("decision") or "hold").upper()
            conf = item.get("confidence", 0.0)
            reason = item.get("reason", "")

            chg_icon = "🔺" if chg_pct > 0 else ("🔻" if chg_pct < 0 else "▫️")

            if dec == "BUY":
                buy_cnt += 1
                icon = "🟢【買進】"
            elif dec == "SELL":
                sell_cnt += 1
                icon = "🔴【賣出/避開】"
            else:
                hold_cnt += 1
                icon = "🟡【觀望/續抱】"

            conf_str = f"{conf*100:.0f}%" if conf > 0 else "--"
            lines.append(
                f"{icon} **{name}** (`{sym}`) 現價: `{price:.2f}` ({chg_icon}{chg_pct:+.2f}%)\n"
                f"└ AI 信賴度: `{conf_str}` | 指引: *{reason[:60]}*"
            )

        fields = [
            {
                "name": f"🎯 標的即時決策矩陣 (共 {len(decisions)} 檔)",
                "value": "\n\n".join(lines[:10]) if lines else "無追蹤標的",
                "inline": False
            },
            {
                "name": "📊 早盤多空態勢速查",
                "value": f"🟢 建議買進: `{buy_cnt}` 檔  |  🔴 建議賣出: `{sell_cnt}` 檔  |  🟡 建議觀望: `{hold_cnt}` 檔\n*本數據將於今日 14:00 收盤後自動結算並對比預測吻合度。*",
                "inline": False
            }
        ]

        return {
            "title": f"⚡【TW_STOCK_DECISION】早盤 10:00 操盤決策發布 ({date_str})",
            "description": "由法人級多維數據（均線/動能/籌碼/借券/風控/CB）結合 Decision 3.0 大模型進行之盤中買賣判定。",
            "color": self.colors["SUMMARY"],
            "fields": fields,
            "footer": {
                "text": "TW_STOCK_DECISION • 系統已將預測存入結論追蹤資料庫"
            }
        }

    def build_afternoon_conclusion_embed(self, date_str: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        下午 14:00 - 收盤驗證與預測吻合結論卡片
        """
        lines = []
        correct_cnt = 0
        total_cnt = len(results)

        for item in results:
            sym = item.get("symbol", "")
            name = item.get("name", sym)
            m_dec = (item.get("morning_decision") or "hold").upper()
            m_price = item.get("morning_price", 0.0)
            a_price = item.get("afternoon_price", 0.0)
            diff_pct = item.get("price_diff_pct", 0.0)
            is_corr = item.get("is_correct", False)
            res_text = item.get("conclusion_result", "")

            if is_corr:
                correct_cnt += 1
                status_icon = "✅ 吻合"
            else:
                status_icon = "❌ 偏差"

            dec_map = {"BUY": "🟢買進", "SELL": "🔴賣出", "HOLD": "🟡觀望"}
            dec_label = dec_map.get(m_dec, m_dec)

            lines.append(
                f"{status_icon} **{name}** (`{sym}`) - 原決策: {dec_label}\n"
                f"├ 早盤: `${m_price:.2f}` ➔ 收盤: `${a_price:.2f}` (盤中變動: `{diff_pct:+.2f}%`)\n"
                f"└ 結論: *{res_text}*"
            )

        acc_pct = (correct_cnt / total_cnt * 100.0) if total_cnt > 0 else 0.0

        if acc_pct >= 70.0:
            color = self.colors["ACCURACY_HIGH"]
            badge = "🔥 絕佳精準度"
        elif acc_pct >= 50.0:
            color = self.colors["ACCURACY_MED"]
            badge = "⚖️ 表現穩健"
        else:
            color = self.colors["ACCURACY_LOW"]
            badge = "⚠️ 盤勢震盪加大"

        fields = [
            {
                "name": f"📝 當日驗收結論明細 ({correct_cnt}/{total_cnt} 吻合)",
                "value": "\n\n".join(lines[:10]) if lines else "無驗收記錄",
                "inline": False
            },
            {
                "name": "🎯 今日預測準確度總計",
                "value": f"**今日勝率**: `{acc_pct:.1f}%` ({badge})\n"
                         f"**已納入累計**: 所有數據已自動寫入資料庫，將於週六進行週報統合統計。",
                "inline": False
            }
        ]

        return {
            "title": f"🏁【TW_STOCK_DECISION】盤後 14:00 預測吻合結論報告 ({date_str})",
            "description": f"比對今日早上 10:00 發布之買賣指引與 13:30 收盤後市場真實行情走勢。",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "TW_STOCK_DECISION • 自動結論系統紀錄完成"
            }
        }

    def build_weekly_summary_embed(self, summary_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        每週六 10:00 - 週統整勝率與回測報告卡片
        """
        period = summary_data.get("period", "")
        total = summary_data.get("total_samples", 0)
        correct = summary_data.get("correct_samples", 0)
        acc = summary_data.get("accuracy_pct", 0.0)
        breakdown = summary_data.get("breakdown", {})
        daily = summary_data.get("daily_breakdown", {})

        daily_lines = []
        for d, info in sorted(daily.items()):
            tot = info.get("total", 0)
            corr = info.get("correct", 0)
            day_acc = (corr / tot * 100.0) if tot > 0 else 0.0
            daily_lines.append(f"• **{d}**：準確率 `{day_acc:.1f}%` ({corr}/{tot} 檔吻合)")

        buy_info = breakdown.get("buy", {})
        sell_info = breakdown.get("sell", {})
        hold_info = breakdown.get("hold", {})

        stats_text = (
            f"• 🟢 **買進決策勝率**：`{buy_info.get('accuracy', 0)}%` (成功 {buy_info.get('correct', 0)}/{buy_info.get('total', 0)} 次)\n"
            f"• 🔴 **賣出避開準確率**：`{sell_info.get('accuracy', 0)}%` (成功 {sell_info.get('correct', 0)}/{sell_info.get('total', 0)} 次)\n"
            f"• 🟡 **盤整觀望命中率**：`{hold_info.get('accuracy', 0)}%` (成功 {hold_info.get('correct', 0)}/{hold_info.get('total', 0)} 次)"
        )

        if acc >= 75.0:
            color = self.colors["ACCURACY_HIGH"]
            grade = "A+ 卓越"
        elif acc >= 60.0:
            color = self.colors["ACCURACY_MED"]
            grade = "B+ 良好"
        else:
            color = self.colors["ACCURACY_LOW"]
            grade = "C 需關注"

        fields = [
            {
                "name": f"🏆 全週整體預測準確度評級：【{grade}】",
                "value": f"• **本週統計區間**：`{period}`\n"
                         f"• **總預測驗證樣本**：`{total}` 次\n"
                         f"• **成功吻合次數**：`{correct}` 次\n"
                         f"• **綜合平均勝率**：`{acc:.1f}%`",
                "inline": False
            },
            {
                "name": "📊 依操作指令分類統計",
                "value": stats_text,
                "inline": False
            },
            {
                "name": "📅 每日勝率走勢清單",
                "value": "\n".join(daily_lines) if daily_lines else "本週暫無連續記錄",
                "inline": False
            }
        ]

        return {
            "title": f"📈【TW_STOCK_DECISION】每週 AI 決策準確度統整報告 ({period})",
            "description": "本報告由系統自動追蹤本週各交易日 10:00 預測與 14:00 收盤結果，經量化回測產出之客觀審查報告。",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "TW_STOCK_DECISION • 每週定期量化回測與績效審查"
            }
        }
