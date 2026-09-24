"""
台灣證券交易所 (TWSE) 與 櫃買中心 (TPEx) 公開資料擷取模組
支援：全體董監持股與設質比率 (上市/上櫃)、可轉換公司債 (CB) 條款與發行資料
"""
from typing import Dict, Any, Optional, List
import io
import logging
import requests
import pandas as pd

logger = logging.getLogger(__name__)

class TWSEOpenDataClient:
    """TWSE/TPEx Open Data 與公開資訊觀測站 (MOPS) 資料客戶端"""

    def __init__(self):
        self._twse_pledge_df: Optional[pd.DataFrame] = None
        self._tpex_pledge_df: Optional[pd.DataFrame] = None
        self._cb_list: Optional[List[Dict[str, Any]]] = None

    def _load_pledge_data(self):
        """下載並快取上市與上櫃的最新董監事持股及設質資料 (每月更新)"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 1. 上市公司董監事持股及設質
        if self._twse_pledge_df is None:
            url_l = "https://mopsfin.twse.com.tw/opendata/t187ap11_L.csv"
            try:
                r = requests.get(url_l, headers=headers, timeout=12)
                if r.status_code == 200:
                    df = pd.read_csv(io.StringIO(r.content.decode("utf-8-sig", errors="ignore")))
                    self._twse_pledge_df = df
                    logger.info(f"成功載入上市公司董監質押資料，共 {len(df)} 筆")
            except Exception as e:
                logger.error(f"下載上市公司董監質押資料失敗: {e}")

        # 2. 上櫃公司董監事持股及設質
        if self._tpex_pledge_df is None:
            url_o = "https://mopsfin.twse.com.tw/opendata/t187ap11_O.csv"
            try:
                r = requests.get(url_o, headers=headers, timeout=12)
                if r.status_code == 200:
                    df = pd.read_csv(io.StringIO(r.content.decode("utf-8-sig", errors="ignore")))
                    self._tpex_pledge_df = df
                    logger.info(f"成功載入上櫃公司董監質押資料，共 {len(df)} 筆")
            except Exception as e:
                logger.error(f"下載上櫃公司董監質押資料失敗: {e}")

    def get_director_pledge_info(self, stock_code: str) -> Dict[str, Any]:
        """
        取得特定股票的董監事持股與質押狀況
        回傳：全體持股數、設質股數、設質比例、風險評級、高質押內部人明細
        """
        self._load_pledge_data()

        # 尋找上市或上櫃資料
        target_rows = None
        for df in [self._twse_pledge_df, self._tpex_pledge_df]:
            if df is not None and not df.empty:
                # 第三欄為公司代號 (如 公司代號 / 公司代碼)
                col_code = df.columns[2]
                matched = df[df[col_code].astype(str).str.strip() == str(stock_code).strip()]
                if not matched.empty:
                    target_rows = matched
                    break

        if target_rows is None or target_rows.empty:
            return {
                "stock_code": stock_code,
                "has_data": False,
                "pledge_ratio": 0.0,
                "total_shares": 0,
                "pledged_shares": 0,
                "risk_level": "未知/無資料",
                "risk_tag": "⚪",
                "high_pledge_directors": []
            }

        try:
            # 欄位解析: 4: 職稱, 5: 姓名, 7: 目前持股, 8: 設質股數, 9: 設質比例
            col_title = target_rows.columns[4]
            col_name = target_rows.columns[5]
            col_hold = target_rows.columns[7]
            col_pledge = target_rows.columns[8]

            total_hold = 0
            total_pledge = 0
            high_pledge_directors = []

            for _, row in target_rows.iterrows():
                try:
                    hold = int(str(row[col_hold]).replace(",", "").strip())
                    pledge = int(str(row[col_pledge]).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue

                total_hold += hold
                total_pledge += pledge

                if hold > 0:
                    indiv_ratio = (pledge / hold) * 100
                    if indiv_ratio >= 30.0:  # 質押比例超過 30% 列為關注對象
                        high_pledge_directors.append({
                            "title": str(row[col_title]).strip(),
                            "name": str(row[col_name]).strip(),
                            "holding_shares": hold,
                            "pledged_shares": pledge,
                            "pledge_ratio": round(indiv_ratio, 2)
                        })

            overall_ratio = (total_pledge / total_hold * 100) if total_hold > 0 else 0.0

            if overall_ratio >= 50.0:
                risk_level = "高危險 (追繳斷頭警示)"
                risk_tag = "🔴"
            elif overall_ratio >= 30.0:
                risk_level = "警戒 (大股東槓桿偏高)"
                risk_tag = "🟡"
            else:
                risk_level = "安全 (質押比率正常)"
                risk_tag = "🟢"

            return {
                "stock_code": stock_code,
                "has_data": True,
                "pledge_ratio": round(overall_ratio, 2),
                "total_shares": total_hold,
                "pledged_shares": total_pledge,
                "risk_level": risk_level,
                "risk_tag": risk_tag,
                "high_pledge_directors": high_pledge_directors
            }
        except Exception as e:
            logger.error(f"解析 {stock_code} 董監質押資料異常: {e}")
            return {
                "stock_code": stock_code,
                "has_data": False,
                "pledge_ratio": 0.0,
                "risk_level": "解析異常",
                "risk_tag": "⚪",
                "high_pledge_directors": []
            }

    def get_convertible_bonds(self, stock_code: str, current_stock_price: float) -> Dict[str, Any]:
        """
        查詢特定股票的可轉換公司債 (CB)，並評估其轉換平價與套利賣壓
        """
        if self._cb_list is None:
            url_cb = "https://www.tpex.org.tw/openapi/v1/bond_ISSBD5_data"
            try:
                r = requests.get(url_cb, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if r.status_code == 200:
                    self._cb_list = r.json()
                    logger.info(f"成功載入櫃買中心 CB 清冊，共 {len(self._cb_list)} 筆")
                else:
                    self._cb_list = []
            except Exception as e:
                logger.error(f"下載 TPEx CB 清冊失敗: {e}")
                self._cb_list = []

        matched_cbs = []
        for cb in self._cb_list:
            issuer = str(cb.get("IssuerCode", "")).strip().lstrip("0")
            if issuer == str(stock_code).strip():
                try:
                    conv_price = float(cb.get("Conversion/ExchangePriceAtIssuance", 0.0))
                except (ValueError, TypeError):
                    conv_price = 0.0

                short_name = cb.get("ShortName", f"{stock_code}可轉債")
                maturity = cb.get("MaturityDate", "")
                put_date = cb.get("PutOptionDate", "")
                outstanding = cb.get("OutstandingAmount", "0")

                # 計算平價 (Parity Value) 與溢價率
                # 平價 = (現價 / 轉換價) * 100
                parity = (current_stock_price / conv_price * 100) if conv_price > 0 else 0.0
                premium_ratio = ((current_stock_price - conv_price) / conv_price * 100) if conv_price > 0 else 0.0

                # 套利賣壓評估
                # 若股價遠高於轉換價 (價內，平價 > 105)，CB 持有人有強烈動機借券放空或轉換現股拋售
                if parity >= 115.0:
                    arbitrage_risk = "極高 (大幅價內，強烈借券套利拋售賣壓)"
                    arbitrage_tag = "🔴"
                elif parity >= 105.0:
                    arbitrage_risk = "偏高 (價內狀態，注意轉換套利賣壓)"
                    arbitrage_tag = "🟡"
                elif parity <= 90.0:
                    arbitrage_risk = "無套利賣壓 (價外，公司臨近賣回日可能有拉抬誘因)"
                    arbitrage_tag = "🟢"
                else:
                    arbitrage_risk = "中立 (接近轉換價附近整理)"
                    arbitrage_tag = "⚪"

                matched_cbs.append({
                    "short_name": short_name,
                    "conversion_price": round(conv_price, 2),
                    "parity": round(parity, 2),
                    "premium_ratio": round(premium_ratio, 2),
                    "maturity_date": maturity,
                    "put_date": put_date,
                    "outstanding_amount": outstanding,
                    "arbitrage_risk": arbitrage_risk,
                    "arbitrage_tag": arbitrage_tag
                })

        has_cb = len(matched_cbs) > 0
        return {
            "stock_code": stock_code,
            "has_cb": has_cb,
            "cb_count": len(matched_cbs),
            "cb_details": matched_cbs,
            "summary": "無發行可轉債 (無可轉債套利賣壓)" if not has_cb else f"已發行 {len(matched_cbs)} 檔可轉債，需留意轉換賣壓"
        }
