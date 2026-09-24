"""
同業與族群表現比對分析模組 (Peer & Sector Relative Performance)
"""
from typing import Dict, Any, List, Optional
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

class PeerAnalyzer:
    def __init__(self):
        pass

    def analyze_peer_comparison(self, target_symbol: str, target_change_pct: float, peer_symbols: List[str]) -> Dict[str, Any]:
        """
        比對個股與同業指標股的漲跌動能，判定是「領頭羊」、「落後補漲」還是「弱勢掉隊」
        """
        peer_results = []
        if not peer_symbols:
            return {
                "has_peers": False,
                "role": "單一個股 (未設定同業)",
                "summary": "未指定同業比較標的",
                "peers": []
            }

        peer_changes = []
        for sym in peer_symbols:
            try:
                t = yf.Ticker(sym)
                h = t.history(period="5d")
                if not h.empty and len(h) >= 2:
                    c = float(h['Close'].iloc[-1])
                    p = float(h['Close'].iloc[-2])
                    pct = round(((c - p) / p * 100), 2) if p else 0.0
                    peer_changes.append(pct)
                    peer_results.append({
                        "symbol": sym,
                        "change_pct": pct,
                        "close": round(c, 2)
                    })
            except Exception as e:
                logger.warning(f"擷取同業 {sym} 失敗: {e}")

        if not peer_changes:
            return {
                "has_peers": False,
                "role": "無同業有效數據",
                "summary": "同業行情連線逾時",
                "peers": []
            }

        avg_peer_pct = round(sum(peer_changes) / len(peer_changes), 2)
        diff = round(target_change_pct - avg_peer_pct, 2)

        if diff >= 1.5:
            role = "族群領頭羊 (強勢領漲)"
            tag = "🟢"
            comment = f"強於同業平均 ({avg_peer_pct:+.2f}%) 達 {diff:+.2f}%，買盤集中，屬族群領攻指標。"
        elif diff <= -1.5:
            role = "弱勢掉隊 (資金排擠)"
            tag = "🔴"
            comment = f"弱於同業平均 ({avg_peer_pct:+.2f}%) 達 {diff:+.2f}%，族群走強但該股買氣渙散，需提防補跌。"
        else:
            role = "同業同步 (族群連動震盪)"
            tag = "🟡"
            comment = f"與同業平均 ({avg_peer_pct:+.2f}%) 走勢同步 (差異 {diff:+.2f}%)，受整體產業風向牽動。"

        return {
            "has_peers": True,
            "target_change_pct": target_change_pct,
            "avg_peer_change_pct": avg_peer_pct,
            "performance_gap": diff,
            "role": role,
            "tag": tag,
            "comment": comment,
            "peer_details": peer_results
        }
