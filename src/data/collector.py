"""
多源數據收集與整合匯流器 (Data Collector)
將 yfinance、FinMind、TWSE/TPEx OpenAPI 資料組合成統一結構
"""
from typing import Dict, Any, List, Optional
import logging
from src.data.market_data import MarketDataClient
from src.data.finmind_client import FinMindClient
from src.data.twse_client import TWSEOpenDataClient
from src.analysis.peer import PeerAnalyzer

logger = logging.getLogger(__name__)

class DataCollector:
    def __init__(self, finmind_token: Optional[str] = None):
        self.market_client = MarketDataClient()
        self.finmind_client = FinMindClient(api_token=finmind_token)
        self.twse_client = TWSEOpenDataClient()
        self.peer_analyzer = PeerAnalyzer()

    def collect_market_overview(self, config_stocks: Dict[str, Any]) -> Dict[str, Any]:
        """收集國際大盤指數與隔夜美股市場概況"""
        indices = config_stocks.get("market_indices", [])
        us_stocks = config_stocks.get("us_stocks", [])
        return self.market_client.get_macro_market_overview(indices, us_stocks)

    def collect_stock_full_profile(self, stock_cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        收集單一股票的全維度數據 (技術面, 籌碼三大法人, 借券賣出, 當沖比, 真假營收, 董監質押, CB, 同業)
        """
        symbol = stock_cfg.get("symbol")
        code = stock_cfg.get("code")
        name = stock_cfg.get("name", code)
        sector = stock_cfg.get("sector", "")
        peers = stock_cfg.get("peers", [])

        logger.info(f"開始收集 {name} ({symbol}) 全維度資料...")

        # 1. 技術面與行情 (yfinance)
        tech_data = self.market_client.get_stock_technical_summary(symbol)
        if not tech_data:
            logger.error(f"無法取得 {symbol} 技術面數據，跳過此檔股票")
            return None

        current_price = tech_data.get("latest_close", 0.0)
        total_vol = tech_data.get("volume", 0)
        change_pct = tech_data.get("change_pct", 0.0)

        # 2. 籌碼面：三大法人買賣超 (FinMind)
        chips_data = self.finmind_client.get_institutional_flows(code, days=25)

        # 3. 籌碼面：借券賣出餘額 (SBL) (FinMind)
        sbl_data = self.finmind_client.get_short_sale_and_sbl(code, days=30)

        # 4. 籌碼面：當沖成交比率 (FinMind)
        day_trading_data = self.finmind_client.get_day_trading_ratio(code, total_volume_shares=total_vol)

        # 5. 基本面：「真假營收」陷阱 (DIO/DSO) (FinMind)
        revenue_trap_data = self.finmind_client.get_revenue_trap_indicators(code)

        # 6. 基本面：最新月營收 (FinMind)
        monthly_rev_data = self.finmind_client.get_latest_monthly_revenue(code)

        # 7. 公司治理：董監事質押比率與內部人 (TWSE/TPEx Open Data)
        pledge_data = self.twse_client.get_director_pledge_info(code)

        # 8. 衍生金融：可轉換公司債 (CB) 套利賣壓 (TPEx Open Data)
        cb_data = self.twse_client.get_convertible_bonds(code, current_stock_price=current_price)

        # 9. 族群連動：同業指標股強弱對比
        peer_data = self.peer_analyzer.analyze_peer_comparison(symbol, change_pct, peers)

        return {
            "code": code,
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "benchmark_us": stock_cfg.get("benchmark_us") or stock_cfg.get("benchmark_adr"),
            "technical": tech_data,
            "chips": chips_data,
            "sbl_short": sbl_data,
            "day_trading": day_trading_data,
            "revenue_trap": revenue_trap_data,
            "monthly_revenue": monthly_rev_data,
            "governance_pledge": pledge_data,
            "convertible_bond": cb_data,
            "peer_comparison": peer_data
        }
