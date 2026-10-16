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

    @staticmethod
    def _chunk_lines_to_fields(title_prefix: str, lines: List[str], max_chars: int = 900) -> List[Dict[str, Any]]:
        """將多行文字切分為不超過 Discord 單一 Field 限制 (1024 字元) 的多個 Fields"""
        if not lines:
            return []
        chunks = []
        cur_lines = []
        cur_len = 0
        for line in lines:
            line_len = len(line) + 2
            if cur_len + line_len > max_chars and cur_lines:
                chunks.append("\n\n".join(cur_lines))
                cur_lines = [line]
                cur_len = line_len
            else:
                cur_lines.append(line)
                cur_len += line_len
        if cur_lines:
            chunks.append("\n\n".join(cur_lines))

        fields = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, 1):
            name = title_prefix if total == 1 else f"{title_prefix} ({idx}/{total})"
            fields.append({
                "name": name[:256],
                "value": chunk[:1024],
                "inline": False
            })
        return fields

    def build_morning_decision_embed(self, date_str: str, decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        早上 10:00 - 盤中 AI 即時決策發布卡片
        """
        buy_lines = []
        sell_lines = []
        hold_lines = []

        for item in decisions:
            sym = item.get("symbol", "")
            name = item.get("name", sym)
            price = item.get("price", 0.0)
            chg_pct = item.get("change_pct", 0.0)
            dec_lower = (item.get("decision") or "hold").lower()
            conf = item.get("confidence", 0.0)
            reason = item.get("reason", "")

            chg_icon = "🔺" if chg_pct > 0 else ("🔻" if chg_pct < 0 else "▫️")
            conf_str = f"{conf*100:.0f}%" if conf > 0 else "--"

            line = (
                f"**{name}** (`{sym}`) 現價: `{price:.2f}` ({chg_icon}{chg_pct:+.2f}%) | 信賴度: `{conf_str}`\n"
                f"└ 指引: *{reason[:85]}*"
            )

            if "buy" in dec_lower or "green" in dec_lower:
                buy_lines.append(f"🟢 {line}")
            elif "sell" in dec_lower or "avoid" in dec_lower or "red" in dec_lower:
                sell_lines.append(f"🔴 {line}")
            else:
                hold_lines.append(f"🟡 {line}")

        fields = []
        if buy_lines:
            fields.extend(self._chunk_lines_to_fields(f"🟢 建議買進標的 (共 {len(buy_lines)} 檔)", buy_lines))
        if sell_lines:
            fields.extend(self._chunk_lines_to_fields(f"🔴 建議避開/賣出 (共 {len(sell_lines)} 檔)", sell_lines))
        if hold_lines:
            fields.extend(self._chunk_lines_to_fields(f"🟡 觀望等待/續抱 (共 {len(hold_lines)} 檔)", hold_lines))

        if not fields:
            fields.append({
                "name": "🎯 標的即時決策矩陣",
                "value": "今日無追蹤標的或無有效信號",
                "inline": False
            })

        fields.append({
            "name": "📊 早盤多空態勢速查",
            "value": f"🟢 建議買進: `{len(buy_lines)}` 檔  |  🔴 建議避開: `{len(sell_lines)}` 檔  |  🟡 建議觀望: `{len(hold_lines)}` 檔\n*本數據將於今日 14:00 收盤後自動結算並對比預測吻合度。*",
            "inline": False
        })

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
        correct_lines = []
        deviated_lines = []
        untracked_lines = []

        total_concluded = 0
        total_correct = 0

        for item in results:
            sym = item.get("symbol", "")
            name = item.get("name", sym)
            m_price = item.get("morning_price", 0.0)
            a_price = item.get("afternoon_price", 0.0)
            diff_pct = item.get("price_diff_pct", 0.0)
            is_corr = item.get("is_correct", False)
            is_untracked = item.get("is_untracked", False)
            res_text = item.get("conclusion_result", "")

            if is_untracked:
                untracked_lines.append(
                    f"▫️ **{name}** (`{sym}`) 收盤: `${a_price:.2f}` ({diff_pct:+.2f}%)\n"
                    f"└ 結論: *{res_text[:85]}*"
                )
                continue

            total_concluded += 1
            m_dec_str = (item.get("morning_decision") or "hold").lower()
            if "buy" in m_dec_str or "green" in m_dec_str:
                dec_label = "🟢買進"
            elif "sell" in m_dec_str or "avoid" in m_dec_str or "red" in m_dec_str:
                dec_label = "🔴賣出/避開"
            else:
                dec_label = "🟡觀望等待"

            line = (
                f"**{name}** (`{sym}`) 原決策: {dec_label}\n"
                f"├ 早盤: `${m_price:.2f}` ➔ 收盤: `${a_price:.2f}` ({diff_pct:+.2f}%)\n"
                f"└ 結論: *{res_text[:85]}*"
            )

            if is_corr:
                total_correct += 1
                correct_lines.append(f"✅ {line}")
            else:
                deviated_lines.append(f"❌ {line}")

        fields = []
        if correct_lines:
            fields.extend(self._chunk_lines_to_fields(f"✅ 預測吻合標的 ({len(correct_lines)} 檔)", correct_lines))
        if deviated_lines:
            fields.extend(self._chunk_lines_to_fields(f"❌ 偏差檢討標的 ({len(deviated_lines)} 檔)", deviated_lines))
        if untracked_lines:
            fields.extend(self._chunk_lines_to_fields(f"📊 盤後收盤總覽 (無早盤對照 {len(untracked_lines)} 檔)", untracked_lines))

        if not fields:
            fields.append({
                "name": "📝 當日驗收結論明細",
                "value": "今日尚無結算數據",
                "inline": False
            })

        if total_concluded > 0:
            acc_pct = (total_correct / total_concluded * 100.0)
            if acc_pct >= 70.0:
                color = self.colors["ACCURACY_HIGH"]
                badge = "🔥 絕佳精準度"
            elif acc_pct >= 50.0:
                color = self.colors["ACCURACY_MED"]
                badge = "⚖️ 表現穩健"
            else:
                color = self.colors["ACCURACY_LOW"]
                badge = "⚠️ 盤勢震盪加大"

            summary_text = (
                f"• **今日勝率**: `{acc_pct:.1f}%` ({badge})\n"
                f"• **有效樣本**: 吻合 `{total_correct}` / 總驗證 `{total_concluded}` 檔\n"
                f"• **歷史資料庫**: 已同步寫入，每週六自動產出週統整報告。"
            )
        else:
            color = self.colors["SUMMARY"]
            summary_text = (
                f"• **當日狀態**: 早盤未執行預測記錄，已先行收錄盤後真實收盤行情。\n"
                f"• **提醒**: 明日 10:00 排程將自動啟用早盤預測並納入對比。"
            )

        fields.append({
            "name": "🎯 今日預測準確度總計",
            "value": summary_text[:1024],
            "inline": False
        })

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
                "value": (
                    f"• **本週統計區間**：`{period}`\n"
                    f"• **總預測驗證樣本**：`{total}` 次\n"
                    f"• **成功吻合次數**：`{correct}` 次\n"
                    f"• **綜合平均勝率**：`{acc:.1f}%`"
                )[:1024],
                "inline": False
            },
            {
                "name": "📊 依操作指令分類統計",
                "value": stats_text[:1024],
                "inline": False
            },
            {
                "name": "📅 每日勝率走勢清單",
                "value": ("\n".join(daily_lines) if daily_lines else "本週暫無連續記錄")[:1024],
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
