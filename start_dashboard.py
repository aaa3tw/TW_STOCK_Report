#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一鍵啟動 Decision 3.0 股票操盤決策系統並自動開啟瀏覽器
"""
import os
import sys
import webbrowser
import threading
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(CURRENT_DIR, "dashboard", "server.py")

def open_browser():
    time.sleep(1.2)
    url = "http://localhost:8888"
    print(f"🌐 正在為您打開 Decision 3.0 決策儀表板: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()
    
    # 執行 server
    from dashboard.server import run_server
    run_server(8888)

