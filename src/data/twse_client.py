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
        self._pledge_dict: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._pledge_attempted: bool = False
        self._cb_list: Optional[List[Dict[str, Any]]] = None
        self._cb_attempted: bool = False

    def _load_pledge_data(self):
        """下載並快取上市/上櫃最新董監事持股及設質資料 (採用 TWSE 官方 OpenAPI JSON 端點)"""
        if self._pledge_attempted:
            return
        self._pledge_attempted = True
        self._pledge_dict = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 1. 台灣證交所上市公司董監質押 OpenAPI (快速 JSON)
        url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap11_L"
        try:
            r = requests.get(url_twse, headers=headers, timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                for row in data:
                    code = str(row.get("公司代號", "")).strip()
                    if code:
                        if code not in self._pledge_dict:
                            self._pledge_dict[code] = []
                        self._pledge_dict[code].append(row)
                logger.info(f"成功載入上市公司董監質押資料，共涵蓋 {len(self._pledge_dict)} 家企業")
        except Exception as e:
            logger.warning(f"下載上市公司董監質押 OpenAPI 失敗 (跳過以維持極速): {e}")

    def get_director_pledge_info(self, stock_code: str) -> Dict[str, Any]:
        """
        取得特定股票的董監事持股與質押狀況 (O(1) 毫秒級查表)
        回傳：全體持股數、設質股數、設質比例、風險評級、高質押內部人明細
        """
        self._load_pledge_data()

        code_str = str(stock_code).strip()
        rows = self._pledge_dict.get(code_str) if self._pledge_dict else None

        if not rows:
            return {
                "stock_code": stock_code,
                "has_data": False,
                "pledge_ratio": 0.0,
                "total_shares": 0,
                "pledged_shares": 0,
                "risk_level": "安全 (未達質押公告門檻/無質押)",
                "risk_tag": "🟢",
                "high_pledge_directors": []
            }

        try:
            total_hold = 0
            total_pledge = 0
            high_pledge_directors = []

            for row in rows:
                try:
                    hold = int(str(row.get("目前持股", 0)).replace(",", "").strip())
                    pledge = int(str(row.get("設質股數", 0)).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue

                total_hold += hold
                total_pledge += pledge

                if hold > 0:
                    indiv_ratio = (pledge / hold) * 100
                    if indiv_ratio >= 30.0:  # 質押比例超過 30% 列為關注對象
                        high_pledge_directors.append({
                            "title": str(row.get("職稱", "")).strip(),
                            "name": str(row.get("姓名", "")).strip(),
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
        if not self._cb_attempted and self._cb_list is None:
            self._cb_attempted = True
            url_cb = "https://www.tpex.org.tw/openapi/v1/bond_ISSBD5_data"
            try:
                r = requests.get(url_cb, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5)
                if r.status_code == 200:
                    self._cb_list = r.json()
                    logger.info(f"成功載入櫃買中心 CB 清冊，共 {len(self._cb_list)} 筆")
                else:
                    self._cb_list = []
            except Exception as e:
                logger.warning(f"下載 TPEx CB 清冊失敗 (跳過以維持極速): {e}")
                self._cb_list = []

        if self._cb_list is None:
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
