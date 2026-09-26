#!/usr/bin/env python3
"""
Stock_analysis_skill CLI 執行腳本
供使用者、其他 LLM 或 Agent 直接以命令列形式調用
支援單檔、多檔股票代號，並提供 Markdown 與 JSON 兩種輸出格式。

範例用法:
  python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol 2330.TW
  python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol NVDA --format json
  python skills/Stock_analysis_skill/scripts/run_analysis.py --symbol "2330,NVDA,4551" --output report.md
"""
import sys
import os
import argparse
import json
import logging

# 加入專案路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from skills.Stock_analysis_skill.scripts.analyzer import StockAnalyzer

def safe_print(text: str):
    """跨平台安全終端機輸出 (支援 Windows CP950 與 UTF-8)"""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((str(text) + "\n").encode("utf-8", errors="replace"))
            sys.stdout.flush()
        except Exception:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))

def main():
    parser = argparse.ArgumentParser(
        description="全維度法人級台美股即時分析診斷工具 (Stock_analysis_skill)"
    )
    parser.add_argument(
        "--symbol", "-s",
        type=str,
        required=True,
        help="股票代號 (支援台股如 2330, 2330.TW, 1785.TWO, 或美股如 NVDA, TSM, MU，多檔請用逗號分隔)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="輸出格式：markdown (預設，易於人類與 LLM 閱讀) 或 json (結構化資料)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="",
        help="選填：儲存分析報告之檔案路徑"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="靜音模式，僅輸出最後分析結果，隱藏日誌資訊"
    )

    args = parser.parse_args()

    # 設定日誌級別
    log_level = logging.ERROR if args.quiet else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    analyzer = StockAnalyzer()
    symbols = [s.strip() for s in args.symbol.split(",") if s.strip()]

    results = []
    markdown_chunks = []

    for sym in symbols:
        try:
            data = analyzer.analyze(sym)
            results.append(data)
            markdown_chunks.append(data["markdown_report"])
        except Exception as e:
            err_msg = f"❌ 分析 {sym} 失敗: {e}"
            if not args.quiet:
                safe_print(err_msg)
            results.append({"symbol": sym, "error": str(e)})
            markdown_chunks.append(f"# ❌ 分析失敗: {sym}\n> 錯誤原因: {e}")

    # 格式化輸出
    if args.format == "json":
        final_output = json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2)
    else:
        final_output = "\n\n---\n\n".join(markdown_chunks)

    # 輸出至終端機
    safe_print(final_output)

    # 若指定檔案路徑則儲存
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(final_output)
            if not args.quiet:
                safe_print(f"\n[OK] 報告已成功儲存至: {args.output}")
        except Exception as ex:
            safe_print(f"\n[WARN] 儲存檔案失敗: {ex}")

if __name__ == "__main__":
    main()
