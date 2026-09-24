"""
台股交易日與行事曆檢查工具
"""
from datetime import datetime, date
import pytz

def is_taiwan_trading_day(target_date: date = None) -> bool:
    """
    判斷指定日期是否為台股開市交易日 (週一至週五，排除週末與已知的固定休市日)
    """
    tz = pytz.timezone("Asia/Taipei")
    if target_date is None:
        target_date = datetime.now(tz).date()

    # 週末不開市
    if target_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    # 2026/2025 年主要固定國定假日 (可依證交所公告補充)
    fixed_holidays = {
        # 元旦
        (1, 1),
        # 和平紀念日
        (2, 28),
        # 兒童節與清明節
        (4, 3), (4, 4), (4, 5),
        # 勞動節
        (5, 1),
        # 國慶日
        (10, 10),
    }

    if (target_date.month, target_date.day) in fixed_holidays:
        return False

    return True

def get_current_tw_time() -> str:
    """獲取台灣目前時間字串 (YYYY-MM-DD HH:MM:SS)"""
    tz = pytz.timezone("Asia/Taipei")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def get_current_tw_date() -> str:
    """獲取台灣目前日期字串 (YYYY-MM-DD)"""
    tz = pytz.timezone("Asia/Taipei")
    return datetime.now(tz).strftime("%Y-%m-%d")
