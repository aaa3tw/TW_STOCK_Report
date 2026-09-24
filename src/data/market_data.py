"""
市場行情與技術指標擷取模組 (yfinance 引擎)
支援台股 (.TW / .TWO) 與美股標的、大盤指數與 ADR
"""
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

class MarketDataClient:
    def __init__(self):
        pass

    def get_stock_technical_summary(self, symbol: str, period: str = "6mo") -> Optional[Dict[str, Any]]:
        """
        取得個股歷史數據並計算技術指標 (MA5/10/20/60, KD, MACD, RSI, 支撐壓力, 量價係數)
        """
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df.empty or len(df) < 20:
                logger.warning(f"無法取得足夠的歷史行情資料: {symbol}")
                return None

            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            # 1. 基礎收盤與漲跌
            latest_close = float(close.iloc[-1])
            prev_close = float(close.iloc[-2]) if len(close) > 1 else latest_close
            change = latest_close - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0.0

            latest_open = float(df['Open'].iloc[-1])
            latest_high = float(high.iloc[-1])
            latest_low = float(low.iloc[-1])
            latest_vol = float(volume.iloc[-1])

            # 2. 移動平均線 (Moving Averages)
            ma5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else latest_close
            ma10 = float(close.rolling(10).mean().iloc[-1]) if len(close) >= 10 else latest_close
            ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else latest_close
            ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else latest_close

            # 均線多空排列判定
            if latest_close > ma5 > ma10 > ma20 > ma60:
                ma_trend = "多頭排列 (強勢多方)"
            elif latest_close < ma5 < ma10 < ma20:
                ma_trend = "空頭排列 (弱勢空方)"
            elif latest_close > ma20:
                ma_trend = "站上月線 (多方震盪整理)"
            else:
                ma_trend = "跌破月線 (弱勢整理)"

            # 3. 成交量係數 (Volume Surge Ratio)
            vol_ma5 = float(volume.rolling(5).mean().iloc[-1]) if len(volume) >= 5 else latest_vol
            vol_ratio = (latest_vol / vol_ma5) if vol_ma5 > 0 else 1.0

            # 4. KD 指標 (9, 3, 3)
            kd_period = 9
            low_min = low.rolling(kd_period).min()
            high_max = high.rolling(kd_period).max()
            rsv = (close - low_min) / (high_max - low_min + 1e-8) * 100

            k_list, d_list = [], []
            k, d = 50.0, 50.0
            for r in rsv:
                if np.isnan(r):
                    k_list.append(k)
                    d_list.append(d)
                else:
                    k = (2/3) * k + (1/3) * r
                    d = (2/3) * d + (1/3) * k
                    k_list.append(k)
                    d_list.append(d)

            k_val = round(k_list[-1], 2)
            d_val = round(d_list[-1], 2)
            prev_k = round(k_list[-2], 2) if len(k_list) > 1 else k_val
            prev_d = round(d_list[-2], 2) if len(d_list) > 1 else d_val

            kd_signal = "中立"
            if prev_k <= prev_d and k_val > d_val:
                kd_signal = "低檔黃金交叉 (買訊)" if k_val < 35 else "黃金交叉 (偏多)"
            elif prev_k >= prev_d and k_val < d_val:
                kd_signal = "高檔死亡交叉 (警訊)" if k_val > 75 else "死亡交叉 (轉弱)"
            elif k_val > 80:
                kd_signal = "高檔鈍化 (超買)"
            elif k_val < 20:
                kd_signal = "低檔超賣 (蘊釀反彈)"

            # 5. MACD (12, 26, 9)
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False).mean()
            macd_hist = (dif - dea) * 2

            latest_dif = round(float(dif.iloc[-1]), 2)
            latest_dea = round(float(dea.iloc[-1]), 2)
            latest_hist = round(float(macd_hist.iloc[-1]), 2)
            prev_hist = round(float(macd_hist.iloc[-2]), 2) if len(macd_hist) > 1 else latest_hist

            if latest_hist > 0 and latest_hist > prev_hist:
                macd_status = "紅柱放大 (多頭加速)"
            elif latest_hist > 0 and latest_hist <= prev_hist:
                macd_status = "紅柱縮小 (多方動能趨緩)"
            elif latest_hist < 0 and latest_hist < prev_hist:
                macd_status = "綠柱擴大 (空頭主導)"
            else:
                macd_status = "綠柱收斂 (空方減弱反彈)"

            # 6. RSI (14)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-8)
            rsi = 100 - (100 / (1 + rs))
            latest_rsi = round(float(rsi.iloc[-1]), 2) if not np.isnan(rsi.iloc[-1]) else 50.0

            # 7. 關鍵支撐與壓力位 (近 20 日高低點與均線)
            recent_20_high = round(float(high.iloc[-20:].max()), 2)
            recent_20_low = round(float(low.iloc[-20:].min()), 2)

            return {
                "symbol": symbol,
                "latest_close": latest_close,
                "open": latest_open,
                "high": latest_high,
                "low": latest_low,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(latest_vol),
                "volume_ratio_5d": round(vol_ratio, 2),
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
                "ma_trend": ma_trend,
                "kd": {
                    "k": k_val,
                    "d": d_val,
                    "signal": kd_signal
                },
                "macd": {
                    "dif": latest_dif,
                    "dea": latest_dea,
                    "hist": latest_hist,
                    "status": macd_status
                },
                "rsi14": latest_rsi,
                "support_level": recent_20_low,
                "resistance_level": recent_20_high,
            }
        except Exception as e:
            logger.error(f"擷取 {symbol} 技術指標異常: {e}")
            return None

    def get_macro_market_overview(self, indices: List[Dict[str, str]], us_stocks: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        取得國際主要指數 (費半、標普、那指、台指、櫃買) 與關鍵美股 (NVDA, MU, TSM 等) 盤前快照
        """
        results = {"indices": [], "us_stocks": []}

        # 1. 大盤指數
        for item in indices:
            sym = item.get("symbol")
            name = item.get("name", sym)
            try:
                t = yf.Ticker(sym)
                h = t.history(period="5d")
                if not h.empty:
                    c = float(h['Close'].iloc[-1])
                    p = float(h['Close'].iloc[-2]) if len(h) > 1 else c
                    chg = c - p
                    pct = (chg / p) * 100 if p else 0
                    results["indices"].append({
                        "symbol": sym,
                        "name": name,
                        "close": round(c, 2),
                        "change": round(chg, 2),
                        "change_pct": round(pct, 2)
                    })
            except Exception as e:
                logger.warning(f"擷取指數 {sym} 失敗: {e}")

        # 2. 關鍵美股
        for item in us_stocks:
            sym = item.get("symbol")
            name = item.get("name", sym)
            fallback = item.get("fallback_symbol")
            try:
                t = yf.Ticker(sym)
                h = t.history(period="5d")
                if h.empty and fallback:
                    t = yf.Ticker(fallback)
                    h = t.history(period="5d")
                    name = f"{name} ({fallback})"

                if not h.empty:
                    c = float(h['Close'].iloc[-1])
                    p = float(h['Close'].iloc[-2]) if len(h) > 1 else c
                    chg = c - p
                    pct = (chg / p) * 100 if p else 0
                    results["us_stocks"].append({
                        "symbol": sym,
                        "name": name,
                        "sector": item.get("sector", ""),
                        "close": round(c, 2),
                        "change": round(chg, 2),
                        "change_pct": round(pct, 2),
                        "relevance": item.get("relevance", "")
                    })
            except Exception as e:
                logger.warning(f"擷取美股 {sym} 失敗: {e}")

        return results
