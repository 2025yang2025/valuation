import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 定義半導體與科技股產業分類清單 (可自行擴充)
SECTOR_MAP = {
    # IC 設計 / IP 矽智財 (適用 P/E & PEG 模型)
    "IC_DESIGN": ["NVDA", "AMD", "AVGO", "2454.TW", "3661.TW", "3443.TW", "6643.TW"],
    # 晶圓代工 / 封測 / 重資產 (適用 EV/EBITDA & 簡化 DCF 模型)
    "FOUNDRY_CAPEX": ["TSM", "2330.TW", "3711.TW", "2303.TW", "2379.TW", "ASML", "AMAT"],
    # 記憶體 / 劇烈景氣循環 (適用 P/B 河流區間估值法)
    "MEMORY_CYCLE": ["MU", "2408.TW", "2344.TW", "2451.TW", "WDC"]
}

def send_telegram_message(message):
    """發送訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("未設定 Telegram Token 或 Chat ID，僅輸出至 Terminal：\n", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")

def get_sector_type(ticker_symbol):
    """根據代碼判斷產業估值類別"""
    symbol_upper = ticker_symbol.upper()
    for sector, tickers in SECTOR_MAP.items():
        if symbol_upper in tickers:
            return sector
    return "GENERAL" # 預設一般企業

def evaluate_stock(ticker_symbol):
    """抓取數據並執行產業對應估值"""
    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    
    # 基本數據提取
    stock_name = info.get("shortName", ticker_symbol)
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    eps_ttm = info.get("trailingEps", 0)
    bvps = info.get("bookValue", 0)
    pe_ratio = info.get("trailingPE", 0)
    pb_ratio = info.get("priceToBook", 0)
    
    # 預估數據 (若 API 缺值則設預設值)
    peg_ratio = info.get("pegRatio", 1.2)
    earnings_growth = info.get("earningsGrowth", 0.15) or 0.15
    
    sector_type = get_sector_type(ticker_symbol)
    report_lines = [
        f"🤖 *【半導體/個股自動化估值報告】*",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name})",
        f"💵 **當前股價**：`${current_price:.2f}`",
        f"----------------------------------"
    ]
    
    # -------------------------------------------------------------
    # 邏輯 A: IC 設計 / IP 矽智財 (以 P/E 與 PEG 成長性估值為主)
    # -------------------------------------------------------------
    if sector_type == "IC_DESIGN":
        target_pe = earnings_growth * 100  # 以 PEG = 1 為基準合理 P/E
        fair_price_pe = eps_ttm * target_pe
        discount_price = fair_price_pe * 0.8  # 8 折安全邊際

        report_lines.extend([
            f"🏷️ *估值模型*：`P/E & PEG 成長模型 (輕資產/高研發)`",
            f"• 近四季 EPS：`${eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• 預估盈餘成長率：`{earnings_growth * 100:.1f}%`",
            f"• **PEG=1.0 合理價**：`${fair_price_pe:.2f}` (對應 P/E `{target_pe:.1f}x`)",
            f"• **安全邊際價 (8折)**：`${discount_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 低於安全邊際價！' if current_price <= discount_price else '🟡 股價高於安全邊際，建議追蹤營收成長續航力。'}"
        ])

    # -------------------------------------------------------------
    # 邏輯 B: 晶圓代工 / 封測 / 設備 (以 EV/EBITDA 重資產折舊還原法為主)
    # -------------------------------------------------------------
    elif sector_type == "FOUNDRY_CAPEX":
        enterprise_value = info.get("enterpriseValue", 0)
        ebitda = info.get("ebitda", 1)
        ev_ebitda = info.get("enterpriseToEbitda", 0)
        
        # 假設同業/歷史合理 EV/EBITDA 中位數為 10x ~ 12x (可依市場調整)
        target_ev_ebitda = 11.0 
        # 簡單推算企業價值相對合理目標價的溢扣價比例
        fair_price_ev = current_price * (target_ev_ebitda / ev_ebitda) if ev_ebitda > 0 else current_price
        discount_price = fair_price_ev * 0.85

        report_lines.extend([
            f"🏷️ *估值模型*：`EV/EBITDA 資本支出還原模型 (重資產/高折舊)`",
            f"• 當前 EV/EBITDA：`{ev_ebitda:.2f}x`",
            f"• **產業合理 EV/EBITDA 目標 ({target_ev_ebitda:.1f}x)**：`${fair_price_ev:.2f}`",
            f"• **安全邊際價 (85折)**：`${discount_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 進入估值合理偏低區間！' if current_price <= discount_price else '🟡 產能利用率/折舊仍高，持續觀察擴廠節奏。'}"
        ])

    # -------------------------------------------------------------
    # 邏輯 C: 記憶體 / 景氣循環股 (以 P/B 股價淨值比週期定位為主)
    # -------------------------------------------------------------
    elif sector_type == "MEMORY_CYCLE":
        # 記憶體週期常見 P/B 區間：谷底 0.9x ~ 1.1x，頂峰 2.0x ~ 2.5x
        low_pb, fair_pb, high_pb = 1.0, 1.5, 2.2
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb
        
        report_lines.extend([
            f"🏷️ *估值模型*：`P/B 股價淨值比週期模型 (劇烈景氣循環)`",
            f"• 每股淨值 (BVPS)：`${bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
            f"• **週期谷底買點 (P/B {low_pb}x)**：`${buy_target_price:.2f}`",
            f"• **週期合理價值 (P/B {fair_pb}x)**：`${fair_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 進入景氣谷底建倉區間 (P/B <= 1.0x)' if pb_ratio <= low_pb else ('🔴 處於景氣高點狂歡區 (P/B >= 2.0x)' if pb_ratio >= high_pb else '🟡 處於週期中段，注意報價與減產動向。')}"
        ])

    # -------------------------------------------------------------
    # 邏輯 D: 通用成熟企業 (預設 PE + P/B 綜合評價)
    # -------------------------------------------------------------
    else:
        fair_price = eps_ttm * 15.0  # 以 15 倍 P/E 為成熟企業基準
        report_lines.extend([
            f"🏷️ *估值模型*：`綜合成熟企業模型`",
            f"• 目前 P/E：`{pe_ratio:.1f}x` | P/B：`{pb_ratio:.2f}x`",
            f"• **15倍 P/E 基準合理價**：`${fair_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 股價偏低' if current_price < fair_price else '🟡 股價平實或偏高'}"
        ])

    return "\n".join(report_lines)

if __name__ == "__main__":
    # 測試覆蓋三種半導體型態：NVDA (IC設計)、2330.TW (晶圓代工)、MU (記憶體)
    test_tickers = ["NVDA", "2330.TW", "MU"]
    
    for ticker in test_tickers:
        try:
            report = evaluate_stock(ticker)
            print(report)
            print("\n" + "="*40 + "\n")
            send_telegram_message(report)
        except Exception as e:
            print(f"處理 {ticker} 時發生錯誤: {e}")
