import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 手動補充/特定分類對照表 (其餘未列出的台股/美股會自動走 GENERAL 成熟模型)
SECTOR_MAP = {
    "IC_DESIGN": [
        "NVDA",
        "AMD",
        "AVGO",
        "QCOM",
        "2454.TW",
        "3661.TW",
        "3443.TW",
        "6643.TW",
    ],
    "FOUNDRY_CAPEX": [
        "TSM",
        "2330.TW",
        "3711.TW",
        "2303.TW",
        "2379.TW",
        "ASML",
        "AMAT",
        "LRCX",
    ],
    "AI_MEMORY_HBM": ["MU"],
    "MEMORY_CYCLE": ["2408.TW", "2344.TW", "2451.TW", "WDC", "SNCX"],
}


def get_auto_tickers():
    """自動搜尋並抓取台股與美股半導體標的清單"""
    # 美股核心熱門半導體標的
    us_semicon_tickers = [
        "NVDA",
        "AMD",
        "AVGO",
        "TSM",
        "MU",
        "ASML",
        "AMAT",
        "QCOM",
        "LRCX",
    ]

    # 自動抓取台股半導體業個股 (使用 FinMind 免費 API)
    tw_semicon_tickers = []
    try:
        url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
        res = requests.get(url, timeout=10).json()
        data = res.get("data", [])

        # 過濾出「半導體業」且代碼為 4 碼的普通股
        tw_semicon_tickers = [
            f"{item['stock_id']}.TW"
            for item in data
            if item.get("industry_category") == "半導體業"
            and len(item["stock_id"]) == 4
        ]
        print(
            f"🔍 已自動搜尋並抓取到 {len(tw_semicon_tickers)} 檔台股半導體個股。"
        )
    except Exception as e:
        print(f"⚠️ 自動抓取台股清單失敗，改採預設關鍵標的: {e}")
        tw_semicon_tickers = ["2330.TW", "2454.TW", "3661.TW", "2408.TW"]

    # 合併清單並去重
    full_list = list(dict.fromkeys(us_semicon_tickers + tw_semicon_tickers))
    return full_list


def send_telegram_message(message):
    """發送訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "⚠️ 未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，僅於 Terminal 印出：\n"
        )
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
            print(
                f"❌ Telegram API 拒絕 [{response.status_code}]: {res_data.get('description')}"
            )
    except Exception as e:
        print(f"❌ Telegram 發送失敗: {e}")


def get_accurate_price(stock):
    """雙重校驗即時股價 (30% 防呆護欄)"""
    info = stock.info
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    hist = stock.history(period="5d")
    hist_price = float(hist["Close"].iloc[-1]) if not hist.empty else None

    if not price or price <= 0:
        return hist_price

    if hist_price and (abs(price - hist_price) / hist_price > 0.30):
        print(
            f"⚠️ 股價錯位 (Info: {price}, K線: {hist_price})，修正採用 K線價格。"
        )
        return hist_price

    return price


def get_validated_eps(stock, current_price):
    """EPS 雙重檢測護欄"""
    info = stock.info
    forward_eps = info.get("forwardEps", 0.0) or 0.0
    trailing_eps = info.get("trailingEps", 0.0) or 0.0

    if forward_eps > 0 and (
        current_price / forward_eps < 3.0 or forward_eps > current_price * 0.12
    ):
        if trailing_eps > 0 and (current_price / trailing_eps >= 5.0):
            return trailing_eps, "Trailing EPS"
        else:
            return (current_price / 22.0), "系統校正預估 EPS"

    return (
        (forward_eps if forward_eps > 0 else trailing_eps),
        ("Forward EPS" if forward_eps > 0 else "Trailing EPS"),
    )


def get_sector_type(ticker_symbol):
    """判斷產業估值類別"""
    symbol_upper = ticker_symbol.upper()
    for sector, tickers in SECTOR_MAP.items():
        if symbol_upper in tickers:
            return sector
    return "GENERAL"


def evaluate_stock(ticker_symbol):
    """估值運算核心"""
    stock = yf.Ticker(ticker_symbol)
    info = stock.info

    current_price = get_accurate_price(stock)
    if not current_price or current_price == 0:
        raise ValueError(f"無法取得 {ticker_symbol} 即時股價。")

    stock_name = info.get("shortName", ticker_symbol)
    currency_symbol = "$" if info.get("currency") == "USD" else "NT$"
    eps_val, eps_type = get_validated_eps(stock, current_price)
    bvps = info.get("bookValue", 0.0) or 0.0
    pe_ratio = (
        (current_price / eps_val) if eps_val > 0 else info.get("trailingPE", 0.0)
    )
    pb_ratio = (current_price / bvps) if bvps > 0 else 0.0

    sector_type = get_sector_type(ticker_symbol)

    report_lines = [
        "🤖 *【半導體自動估值日報】*",
        f"🌐 **市場**：{'🇺🇸 美股' if currency_symbol == '$' else '🇹🇼 台股'}",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name})",
        f"💵 **當前股價**：`{currency_symbol}{current_price:.2f}`",
        "----------------------------------",
    ]

    # A: IC 設計
    if sector_type == "IC_DESIGN":
        earnings_growth = info.get("earningsGrowth", 0.15) or 0.15
        target_pe = earnings_growth * 100
        fair_price_pe = eps_val * target_pe
        discount_price = fair_price_pe * 0.8

        report_lines.extend(
            [
                "🏷️ *估值模型*：`P/E & PEG 成長模型`",
                f"• EPS ({eps_type})：`{currency_symbol}{eps_val:.2f}` | P/E：`{pe_ratio:.1f}x`",
                f"• 預估成長率：`{earnings_growth * 100:.1f}%`",
                f"• **PEG=1.0 合理價**：`{currency_symbol}{fair_price_pe:.2f}`",
                f"• **安全邊際價 (8折)**：`{currency_symbol}{discount_price:.2f}`",
                f"\n💡 *訊號*：{'🟢 低於安全邊際價！' if current_price <= discount_price else '🟡 高於安全邊際，觀察成長續航力。'}",
            ]
        )

    # B: 晶圓代工 / 重資產
    elif sector_type == "FOUNDRY_CAPEX":
        ev_ebitda = info.get("enterpriseToEbitda", 0.0) or 0.0
        target_ev_ebitda = 11.0
        fair_price_ev = (
            current_price * (target_ev_ebitda / ev_ebitda)
            if ev_ebitda > 0
            else current_price
        )
        discount_price = fair_price_ev * 0.85

        report_lines.extend(
            [
                "🏷️ *估值模型*：`EV/EBITDA 重資產模型`",
                f"• 當前 EV/EBITDA：`{ev_ebitda:.2f}x`",
                f"• **目標 ({target_ev_ebitda:.1f}x) 合理價**：`{currency_symbol}{fair_price_ev:.2f}`",
                f"• **安全邊際價 (85折)**：`{currency_symbol}{discount_price:.2f}`",
                f"\n💡 *訊號*：{'🟢 估值合理偏低！' if current_price <= discount_price else '🟡 產能折舊仍高，持續觀察擴廠。'}",
            ]
        )

    # C: AI 記憶體 / HBM
    elif sector_type == "AI_MEMORY_HBM":
        low_pe, fair_pe, high_pe = 15.0, 20.0, 25.0
        bull_target_price = eps_val * high_pe
        fair_price = eps_val * fair_pe
        buy_target_price = eps_val * low_pe

        status = (
            "🟢 估值低檔建倉區。"
            if current_price <= buy_target_price
            else (
                "🔵 處於合理估值區。"
                if current_price <= fair_price
                else (
                    "🟡 已反映樂觀預期。"
                    if current_price <= bull_target_price
                    else "🔴 高於樂觀目標，注意風險。"
                )
            )
        )

        report_lines.extend(
            [
                f"🏷️ *估值模型*：`HBM P/E 高成長模型 ({eps_type})`",
                f"• BVPS：`{currency_symbol}{bvps:.2f}` | P/B：`{pb_ratio:.2f}x`",
                f"• EPS：`{currency_symbol}{eps_val:.2f}` | P/E：`{pe_ratio:.2f}x`",
                f"• 🎯 **樂觀價 (25x)**：`{currency_symbol}{bull_target_price:.2f}`",
                f"• ⚖️ **合理價 (20x)**：`{currency_symbol}{fair_price:.2f}`",
                f"• 💰 **低檔價 (15x)**：`{currency_symbol}{buy_target_price:.2f}`",
                f"\n💡 *綜合評估*：{status}",
            ]
        )

    # D: 傳統記憶體 (P/B 週期)
    elif sector_type == "MEMORY_CYCLE":
        low_pb, fair_pb, high_pb = 1.0, 1.5, 2.2
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb

        report_lines.extend(
            [
                "🏷️ *估值模型*：`P/B 週期模型`",
                f"• BVPS：`{currency_symbol}{bvps:.2f}` | P/B：`{pb_ratio:.2f}x`",
                f"• **谷底買點 (P/B {low_pb}x)**：`{currency_symbol}{buy_target_price:.2f}`",
                f"• **合理價值 (P/B {fair_pb}x)**：`{currency_symbol}{fair_price:.2f}`",
                f"\n💡 *訊號*：{'🟢 景氣谷底建倉區' if pb_ratio <= low_pb else ('🔴 景氣高點狂歡區' if pb_ratio >= high_pb else '🟡 週期中段，關注報價。')}",
            ]
        )

    # E: 一般通用模型
    else:
        fair_price = eps_val * 15.0
        report_lines.extend(
            [
                "🏷️ *估值模型*：`綜合成熟企業模型`",
                f"• 目前 P/E：`{pe_ratio:.1f}x` | P/B：`{pb_ratio:.2f}x`",
                f"• **15倍 P/E 基準合理價**：`{currency_symbol}{fair_price:.2f}`",
                f"\n💡 *訊號*：{'🟢 股價偏低' if current_price < fair_price else '🟡 股價平實或偏高'}",
            ]
        )

    return "\n".join(report_lines)


def run_job():
    """執行全自動檢索與推播"""
    all_tickers = get_auto_tickers()
    print(f"🚀 開始評估共 {len(all_tickers)} 檔台美股標的...\n")

    for ticker in all_tickers:
        try:
            report = evaluate_stock(ticker)
            print(report)
            print("\n" + "=" * 40 + "\n")
            send_telegram_message(report)
        except Exception as e:
            print(f"⚠️ 跳過 {ticker} (無法取得資料或計算異常): {e}")


if __name__ == "__main__":
    run_job()
