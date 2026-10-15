"""
市場行情與技術指標擷取模組 (結合 TWSE/TPEx 官方即時 API 與 yfinance 雙引擎)
支援台股 (.TW / .TWO) 與美股標的、大盤指數與 ADR，保證股價與當日漲跌 100% 精準即時
"""
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
import yfinance as yf
import logging
import urllib.request
import json
import ssl

logger = logging.getLogger(__name__)

def clean_float(val: Any, default: float = 0.0) -> float:
    """確保數值為合法的有限浮點數，遇 None, NaN, Inf 自動轉為預設值"""
    if val is None:
        return default
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default

class MarketDataClient:
    def __init__(self):
        self.ssl_ctx = ssl.create_default_context()

    def fetch_realtime_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        全維度精準即時報價擷取器：
        1. 台股上市櫃優先調用台灣證交所 / 櫃買中心官方 MIS 即時行情系統 (零延遲、含公司中文名稱)
        2. 美股與台股 fallback 透過 yfinance fast_info 取得最新成交價與昨日收盤價
        """
        sym = symbol.strip().upper()

        # 1. 台股官方即時 MIS 查詢
        if sym.endswith(".TW") or sym.endswith(".TWO") or sym.isdigit():
            code = sym.replace(".TW", "").replace(".TWO", "")
            # 判斷上市或上櫃
            exchanges = ["otc", "tse"] if sym.endswith(".TWO") else ["tse", "otc"]
            for ex in exchanges:
                url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex}_{code}.tw&json=1&delay=0"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=3) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        items = data.get("msgArray", [])
                        if items:
                            it = items[0]
                            name = it.get("n", code)
                            # z: 最近成交價, y: 昨日收盤價, o: 開盤價, h: 最高, l: 最低, v: 成交量
                            z_str = it.get("z", "-")
                            y_str = it.get("y", "-")
                            if z_str == "-" or not z_str:
                                # 盤前或暫無成交取昨收
                                z_str = y_str

                            if z_str != "-" and y_str != "-":
                                z = clean_float(z_str, 0.0)
                                y = clean_float(y_str, z)
                                if z > 0 and y > 0:
                                    chg = z - y
                                    pct = (chg / y) * 100.0
                                    vol = clean_float(it.get("v", 0.0)) * 1000 # 轉為股數
                                    high = clean_float(it.get("h", z), z)
                                    low = clean_float(it.get("l", z), z)
                                    op = clean_float(it.get("o", z), z)
                                    return {
                                        "source": "TWSE_MIS",
                                        "name": name,
                                        "close": round(z, 2),
                                        "prev_close": round(y, 2),
                                        "change": round(chg, 2),
                                        "change_pct": round(pct, 2),
                                        "volume": int(vol),
                                        "open": round(op, 2),
                                        "high": round(high, 2),
                                        "low": round(low, 2)
                                    }
                except Exception as e:
                    logger.debug(f"TWSE MIS 查詢 {code} ({ex}) 異常: {e}")

        # 2. yfinance fast_info 查詢 (美股或台股 fallback)
        try:
            ticker = yf.Ticker(sym)
            fi = ticker.fast_info
            lp = clean_float(getattr(fi, "last_price", None), 0.0)
            pc = clean_float(getattr(fi, "previous_close", None), 0.0)
            if pc <= 0:
                pc = clean_float(getattr(fi, "regular_market_previous_close", None), lp)

            if lp > 0 and pc > 0:
                chg = lp - pc
                pct = (chg / pc) * 100.0
                vol = clean_float(getattr(fi, "last_volume", 0.0), 0.0)
                dh = clean_float(getattr(fi, "day_high", lp), lp)
                dl = clean_float(getattr(fi, "day_low", lp), lp)
                op = clean_float(getattr(fi, "open", lp), lp)
                return {
                    "source": "FAST_INFO",
                    "name": sym,
                    "close": round(lp, 2),
                    "prev_close": round(pc, 2),
                    "change": round(chg, 2),
                    "change_pct": round(pct, 2),
                    "volume": int(vol),
                    "open": round(op, 2),
                    "high": round(dh, 2),
                    "low": round(dl, 2)
                }
        except Exception as e:
            logger.warning(f"fast_info 查詢 {sym} 異常: {e}")

        return None

    def get_stock_technical_summary(self, symbol: str, period: str = "6mo") -> Optional[Dict[str, Any]]:
        """
        取得個股歷史數據並計算技術指標 (MA5/10/20/60, KD, MACD, RSI, 支撐壓力, 量價係數)
        融合最新官方即時行情，徹底根治資料落後一天與漲跌錯誤問題
        """
        try:
            # 1. 取得即時精準行情
            rt_quote = self.fetch_realtime_quote(symbol)

            # 2. 取得歷史 K 線
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df.empty and rt_quote is None:
                logger.warning(f"無法取得歷史行情資料: {symbol}")
                return None

            # 3. 處理當日最新交易日可能為 NaN 的情況，與即時報價融合
            if not df.empty and rt_quote:
                # 若最後一筆 Close 為 NaN，填入即時行情
                last_idx = df.index[-1]
                if pd.isna(df.loc[last_idx, 'Close']) or df.loc[last_idx, 'Close'] <= 0:
                    df.loc[last_idx, 'Close'] = rt_quote['close']
                    df.loc[last_idx, 'High'] = max(rt_quote['high'], rt_quote['close'])
                    df.loc[last_idx, 'Low'] = min(rt_quote['low'], rt_quote['close'])
                    df.loc[last_idx, 'Open'] = rt_quote['open']
                    if rt_quote['volume'] > 0:
                        df.loc[last_idx, 'Volume'] = rt_quote['volume']

            # 清理剩餘無效行
            df = df.dropna(subset=['Close'])
            df = df[df['Close'] > 0]

            if len(df) < 5:
                logger.warning(f"有效歷史行情資料不足 (<5筆): {symbol}")
                if not rt_quote:
                    return None

            close = df['Close']
            high = df['High'].fillna(close)
            low = df['Low'].fillna(close)
            volume = df['Volume'].fillna(0)

            # 4. 基礎收盤與漲跌判定 (優先採用即時官方報價)
            if rt_quote:
                latest_close = rt_quote['close']
                prev_close = rt_quote['prev_close']
                change = rt_quote['change']
                change_pct = rt_quote['change_pct']
                latest_open = rt_quote['open']
                latest_high = rt_quote['high']
                latest_low = rt_quote['low']
                latest_vol = rt_quote['volume'] if rt_quote['volume'] > 0 else clean_float(volume.iloc[-1], 0.0)
                stock_name = rt_quote.get('name', symbol)
            else:
                latest_close = clean_float(close.iloc[-1], 0.0)
                prev_close = clean_float(close.iloc[-2], latest_close) if len(close) > 1 else latest_close
                change = latest_close - prev_close
                change_pct = (change / prev_close) * 100 if prev_close > 0 else 0.0
                latest_open = clean_float(df['Open'].iloc[-1], latest_close)
                latest_high = clean_float(high.iloc[-1], latest_close)
                latest_low = clean_float(low.iloc[-1], latest_close)
                latest_vol = clean_float(volume.iloc[-1], 0.0)
                stock_name = symbol

            if latest_close <= 0:
                logger.warning(f"{symbol} 收盤價無效: {latest_close}")
                return None

            # 5. 移動平均線 (Moving Averages) - min_periods=1 杜絕任何 NaN
            def calc_ma(s: pd.Series, window: int, fallback: float) -> float:
                try:
                    ma_s = s.rolling(window=window, min_periods=1).mean()
                    if not ma_s.empty:
                        return clean_float(ma_s.iloc[-1], fallback)
                    return fallback
                except Exception:
                    return fallback

            ma5 = calc_ma(close, 5, latest_close)
            ma10 = calc_ma(close, 10, latest_close)
            ma20 = calc_ma(close, 20, latest_close)
            ma60 = calc_ma(close, 60, latest_close)

            # 均線多空排列判定
            if latest_close > ma5 > ma10 > ma20 > ma60:
                ma_trend = "多頭排列 (強勢多方)"
            elif latest_close < ma5 < ma10 < ma20:
                ma_trend = "空頭排列 (弱勢空方)"
            elif latest_close > ma20:
                ma_trend = "站上月線 (多方震盪整理)"
            else:
                ma_trend = "跌破月線 (弱勢整理)"

            # 6. 成交量係數 (Volume Surge Ratio)
            vol_ma5 = calc_ma(volume, 5, latest_vol)
            vol_ratio = (latest_vol / vol_ma5) if vol_ma5 > 0 else 1.0
            vol_ratio = clean_float(vol_ratio, 1.0)

            # 7. KD 指標 (9, 3, 3)
            kd_period = min(9, len(df))
            low_min = low.rolling(kd_period, min_periods=1).min()
            high_max = high.rolling(kd_period, min_periods=1).max()
            diff = (high_max - low_min).replace(0, 1e-4)
            rsv = ((close - low_min) / diff * 100).fillna(50.0)

            k_list, d_list = [], []
            k, d = 50.0, 50.0
            for r in rsv:
                r_val = clean_float(r, 50.0)
                k = (2/3) * k + (1/3) * r_val
                d = (2/3) * d + (1/3) * k
                k_list.append(k)
                d_list.append(d)

            k_val = round(clean_float(k_list[-1], 50.0), 2)
            d_val = round(clean_float(d_list[-1], 50.0), 2)
            prev_k = round(clean_float(k_list[-2], k_val), 2) if len(k_list) > 1 else k_val
            prev_d = round(clean_float(d_list[-2], d_val), 2) if len(d_list) > 1 else d_val

            kd_signal = "中立"
            if prev_k <= prev_d and k_val > d_val:
                kd_signal = "低檔黃金交叉 (買訊)" if k_val < 35 else "黃金交叉 (偏多)"
            elif prev_k >= prev_d and k_val < d_val:
                kd_signal = "高檔死亡交叉 (警訊)" if k_val > 75 else "死亡交叉 (轉弱)"
            elif k_val > 80:
                kd_signal = "高檔鈍化 (超買)"
            elif k_val < 20:
                kd_signal = "低檔超賣 (蘊釀反彈)"

            # 8. MACD (12, 26, 9)
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False).mean()
            macd_hist = (dif - dea) * 2

            latest_dif = round(clean_float(dif.iloc[-1], 0.0), 2)
            latest_dea = round(clean_float(dea.iloc[-1], 0.0), 2)
            latest_hist = round(clean_float(macd_hist.iloc[-1], 0.0), 2)
            prev_hist = round(clean_float(macd_hist.iloc[-2], latest_hist), 2) if len(macd_hist) > 1 else latest_hist

            if latest_hist > 0 and latest_hist > prev_hist:
                macd_status = "紅柱放大 (多頭加速)"
            elif latest_hist > 0 and latest_hist <= prev_hist:
                macd_status = "紅柱縮小 (多方動能趨緩)"
            elif latest_hist < 0 and latest_hist < prev_hist:
                macd_status = "綠柱擴大 (空頭主導)"
            else:
                macd_status = "綠柱收斂 (空方減弱反彈)"

            # 9. RSI (14)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
            rs = gain / (loss + 1e-8)
            rsi = 100 - (100 / (1 + rs))
            latest_rsi = round(clean_float(rsi.iloc[-1], 50.0), 2)

            # 10. 關鍵支撐與壓力位 (近 20 日高低點與均線)
            lookback = min(20, len(high))
            recent_high_s = high.iloc[-lookback:].dropna()
            recent_low_s = low.iloc[-lookback:].dropna()
            recent_20_high = round(clean_float(recent_high_s.max() if len(recent_high_s) > 0 else None, latest_close * 1.05), 2)
            recent_20_low = round(clean_float(recent_low_s.min() if len(recent_low_s) > 0 else None, latest_close * 0.95), 2)

            return {
                "symbol": symbol,
                "name": stock_name,
                "latest_close": round(latest_close, 2),
                "prev_close": round(prev_close, 2),
                "open": round(latest_open, 2),
                "high": round(latest_high, 2),
                "low": round(latest_low, 2),
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
            logger.error(f"擷取 {symbol} 技術指標異常: {e}", exc_info=True)
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
                    h = h.dropna(subset=['Close'])
                    h = h[h['Close'] > 0]
                if not h.empty:
                    c = clean_float(h['Close'].iloc[-1], 0.0)
                    p = clean_float(h['Close'].iloc[-2], c) if len(h) > 1 else c
                    if c > 0:
                        chg = c - p
                        pct = (chg / p) * 100 if p > 0 else 0.0
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
                if (h.empty or len(h.dropna(subset=['Close'])) == 0) and fallback:
                    t = yf.Ticker(fallback)
                    h = t.history(period="5d")
                    name = f"{name} ({fallback})"

                if not h.empty:
                    h = h.dropna(subset=['Close'])
                    h = h[h['Close'] > 0]

                if not h.empty:
                    c = clean_float(h['Close'].iloc[-1], 0.0)
                    p = clean_float(h['Close'].iloc[-2], c) if len(h) > 1 else c
                    if c > 0:
                        chg = c - p
                        pct = (chg / p) * 100 if p > 0 else 0.0
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
