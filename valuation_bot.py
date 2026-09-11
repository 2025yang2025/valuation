import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets / Local Env)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 定義產業分類地圖
SECTOR_MAP = {
    # IC 設計 / IP 矽智財 (適用 P/E & PEG 模型)
    "IC_DESIGN": ["NVDA", "AMD", "AVGO", "2454.TW", "3661.TW", "3443.TW", "6643.TW"],
    # 晶圓代工 / 封測 / 重資產 (適用 EV/EBITDA 模型)
    "FOUNDRY_CAPEX": ["TSM", "2330.TW", "3711.TW", "2303.TW", "2379.TW", "ASML", "AMAT"],
    # AI 記憶體 / HBM 高成長 (適用 P/E 雙軌模型)
    "AI_MEMORY_HBM": ["MU"],
    # 傳統記憶體 / 劇烈景氣循環 (適用 P/B 週期模型)
    "MEMORY_CYCLE": ["2408.TW", "2344.TW", "2451.TW", "WDC"]
}

def send_telegram_message(message):
    """發送訊息至 Telegram 並紀錄輸出狀態"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 未設定 Telegram Token 或 Chat ID，僅輸出至 Terminal：\n")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        res_data = response.json()
        if res_data.get("ok"):
            print("✅ Telegram 訊息發送成功！")
        else:
            print(f"❌ Telegram API 拒絕請求 [{response.status_code}]: {res_data.get('description')}")
    except Exception as e:
        print(f"❌ 發送 Telegram 訊息時發生網路或 API 錯誤: {e}")

def get_accurate_price(stock):
    """雙重校驗以取得真實即時股價 (30% 爆價防呆護欄)"""
    info = stock.info
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    hist = stock.history(period="5d")
    hist_price = float(hist["Close"].iloc[-1]) if not hist.empty else None

    if not price or price <= 0:
        return hist_price

    if hist_price and (abs(price - hist_price) / hist_price > 0.30):
        print(f"⚠️ 股價數據異常錯位 (Info: {price}, K線: {hist_price})，已修正採用 K線價格。")
        return hist_price

    return price

def get_validated_eps(stock, current_price):
    """EPS 雙重檢測護欄：防止 yfinance 抓到暴增的錯誤預估 EPS"""
    info = stock.info
    forward_eps = info.get("forwardEps", 0.0) or 0.0
    trailing_eps = info.get("trailingEps", 0.0) or 0.0

    if forward_eps > 0 and (current_price / forward_eps < 3.0 or forward_eps > current_price * 0.12):
        print(f"⚠️ 偵測到極端異常 Forward EPS (${forward_eps:.2f})，自動降級採用 Trailing EPS 或校正值。")
        if trailing_eps > 0 and (current_price / trailing_eps >= 5.0):
            return trailing_eps, "Trailing EPS"
        else:
            corrected_eps = current_price / 22.0
            return corrected_eps, "系統校正預估 EPS"

    return (forward_eps if forward_eps > 0 else trailing_eps), ("Forward EPS" if forward_eps > 0 else "Trailing EPS")

def get_sector_type(ticker_symbol):
    """根據代碼判斷產業估值類別"""
    symbol_upper = ticker_symbol.upper()
    for sector, tickers in SECTOR_MAP.items():
        if symbol_upper in tickers:
            return sector
    return "GENERAL"

def evaluate_stock(ticker_symbol):
    """抓取數據並執行對應估值邏輯"""
    stock = yf.Ticker(ticker_symbol)
    info = stock.info

    current_price = get_accurate_price(stock)
    if not current_price or current_price == 0:
        raise ValueError(f"無法取得 {ticker_symbol} 即時股價。")

    stock_name = info.get("shortName", ticker_symbol)
    currency_symbol = "$" if info.get("currency") == "USD" else "NT$"
    eps_val, eps_type = get_validated_eps(stock, current_price)
    bvps = info.get("bookValue", 0.0) or 0.0
    pe_ratio = (current_price / eps_val) if eps_val > 0 else info.get("trailingPE", 0.0)
    pb_ratio = (current_price / bvps) if bvps > 0 else 0.0

    sector_type = get_sector_type(ticker_symbol)

    report_lines = [
        "🤖 *【半導體/個股自動化估值報告】*",
        f"🌐 **市場**：{'🇺🇸 美股' if currency_symbol == '$' else '🇹🇼 台股'}",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name})",
        f"💵 **當前股價**：`{currency_symbol}{current_price:.2f}`",
        "----------------------------------"
    ]

    # -------------------------------------------------------------
    # 模型 A: IC 設計 / IP 矽智財 (P/E & PEG 成長模型)
    # -------------------------------------------------------------
    if sector_type == "IC_DESIGN":
        earnings_growth = info.get("earningsGrowth", 0.15) or 0.15
        target_pe = earnings_growth * 100
        fair_price_pe = eps_val * target_pe
        discount_price = fair_price_pe * 0.8

        report_lines.extend([
            "🏷️ *估值模型*：`P/E & PEG 成長模型 (輕資產/高研發)`",
            f"• 採計 EPS ({eps_type})：`{currency_symbol}{eps_val:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• 預估盈餘成長率：`{earnings_growth * 100:.1f}%`",
            f"• **PEG=1.0 合理價**：`{currency_symbol}{fair_price_pe:.2f}` (對應 P/E `{target_pe:.1f}x`)",
            f"• **安全邊際價 (8折)**：`{currency_symbol}{discount_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 低於安全邊際價！' if current_price <= discount_price else '🟡 股價高於安全邊際，建議追蹤營收成長續航力。'}"
        ])

    # -------------------------------------------------------------
    # 模型 B: 晶圓代工 / 封測 / 設備 (EV/EBITDA 資本支出模型)
    # -------------------------------------------------------------
    elif sector_type == "FOUNDRY_CAPEX":
        ev_ebitda = info.get("enterpriseToEbitda", 0.0) or 0.0
        target_ev_ebitda = 11.0
        fair_price_ev = current_price * (target_ev_ebitda / ev_ebitda) if ev_ebitda > 0 else current_price
        discount_price = fair_price_ev * 0.85

        report_lines.extend([
            "🏷️ *估值模型*：`EV/EBITDA 資本支出還原模型 (重資產/高折舊)`",
            f"• 當前 EV/EBITDA：`{ev_ebitda:.2f}x`",
            f"• **產業合理目標 ({target_ev_ebitda:.1f}x)**：`{currency_symbol}{fair_price_ev:.2f}`",
            f"• **安全邊際價 (85折)**：`{currency_symbol}{discount_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 進入估值合理偏低區間！' if current_price <= discount_price else '🟡 產能利用率/折舊仍高，持續觀察擴廠節奏。'}"
        ])

    # -------------------------------------------------------------
    # 模型 C: AI 記憶體 / HBM (P/E 高成長與階段評估)
    # -------------------------------------------------------------
    elif sector_type == "AI_MEMORY_HBM":
        low_pe, fair_pe, high_pe = 15.0, 20.0, 25.0
        bull_target_price = eps_val * high_pe
        fair_price = eps_val * fair_pe
        buy_target_price = eps_val * low_pe

        if current_price <= buy_target_price:
            status = "🟢 估值處於低檔建倉區，具備安全邊際。"
        elif current_price <= fair_price:
            status = "🔵 股價處於合理估值區間。"
        elif current_price <= bull_target_price:
            status = "🟡 股價已反映樂觀獲利預期。"
        else:
            status = "🔴 股價高於樂觀預估目標，留意追高風險。"

        report_lines.extend([
            f"🏷️ *估值模型*：`HBM P/E 高成長模型 ({eps_type})`",
            f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
            f"• 採計 EPS ({eps_type})：`{currency_symbol}{eps_val:.2f}` | 目前 P/E：`{pe_ratio:.2f}x`",
            f"• 🎯 **樂觀目標 (P/E {high_pe:.0f}x)**：`{currency_symbol}{bull_target_price:.2f}`",
            f"• ⚖️ **合理價值 (P/E {fair_pe:.0f}x)**：`{currency_symbol}{fair_price:.2f}`",
            f"• 💰 **低檔買點 (P/E {low_pe:.0f}x)**：`{currency_symbol}{buy_target_price:.2f}`",
            f"\n💡 *綜合評估*：{status}"
        ])

    # -------------------------------------------------------------
    # 模型 D: 傳統記憶體 (P/B 股價淨值比週期模型)
    # -------------------------------------------------------------
    elif sector_type == "MEMORY_CYCLE":
        low_pb, fair_pb, high_pb = 1.0, 1.5, 2.2
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb

        report_lines.extend([
            "🏷️ *估值模型*：`P/B 股價淨值比週期模型 (劇烈景氣循環)`",
            f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
            f"• **週期谷底買點 (P/B {low_pb}x)**：`{currency_symbol}{buy_target_price:.2f}`",
            f"• **週期合理價值 (P/B {fair_pb}x)**：`{currency_symbol}{fair_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 進入景氣谷底建倉區間 (P/B <= 1.0x)' if pb_ratio <= low_pb else ('🔴 處於景氣高點狂歡區 (P/B >= 2.0x)' if pb_ratio >= high_pb else '🟡 處於週期中段，注意報價與減產動向。')}"
        ])

    # -------------------------------------------------------------
    # 模型 E: 通用成熟企業
    # -------------------------------------------------------------
    else:
        fair_price = eps_val * 15.0
        report_lines.extend([
            "🏷️ *估值模型*：`綜合成熟企業模型`",
            f"• 目前 P/E：`{pe_ratio:.1f}x` | P/B：`{pb_ratio:.2f}x`",
            f"• **15倍 P/E 基準合理價**：`{currency_symbol}{fair_price:.2f}`",
            f"\n💡 *訊號*：{'🟢 股價偏低' if current_price < fair_price else '🟡 股價平實或偏高'}"
        ])

    return "\n".join(report_lines)

def run_job():
    """執行測試清單並發送 Telegram 推播"""
    test_tickers = ["NVDA", "2330.TW", "MU", "2408.TW"]

    for ticker in test_tickers:
        try:
            report = evaluate_stock(ticker)
            print(report)
            print("\n" + "=" * 40 + "\n")
            send_telegram_message(report)
        except Exception as e:
            print(f"❌ 處理 {ticker} 時發生錯誤: {e}")

if __name__ == "__main__":
    run_job()
