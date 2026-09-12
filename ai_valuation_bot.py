import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 精選台美股前 10 大半導體指標股
TOP_10_TICKERS = [
    # 美股前 5 大指標股
    "NVDA",  # 輝達 (AI 晶片龍頭)
    "AVGO",  # 博通 (客製化 ASIC / 網通)
    "MU",  # 美光 (HBM / 記憶體)
    "AMD",  # 超微 (CPU / GPU)
    "QCOM",  # 高通 (通訊 IC 設計)
    # 台股前 5 大指標股
    "2330.TW",  # 台積電 (晶圓代工龍頭)
    "2454.TW",  # 聯發科 (IC 設計龍頭)
    "3711.TW",  # 日月光投控 (封測龍頭)
    "3661.TW",  # 世芯-KY (IP/ASIC 設計)
    "2408.TW",  # 南亞科 (記憶體指標)
]

# 3. 產業分類對照表
SECTOR_MAP = {
    "IC_DESIGN": ["NVDA", "AMD", "AVGO", "QCOM", "2454.TW", "3661.TW"],
    "FOUNDRY_CAPEX": ["2330.TW", "3711.TW"],
    "AI_MEMORY_HBM": ["MU"],
    "MEMORY_CYCLE": ["2408.TW"],
}

# 4. 中文名稱對照表
STOCK_NAME_ZH = {
    "NVDA": "輝達",
    "AVGO": "博通",
    "MU": "美光",
    "AMD": "超微",
    "QCOM": "高通",
    "2330.TW": "台積電",
    "2454.TW": "聯發科",
    "3711.TW": "日月光投控",
    "3661.TW": "世芯-KY",
    "2408.TW": "南亞科",
}


def get_display_name(ticker_symbol, info):
    """取得中文名稱，若無對照則使用預設名稱"""
    symbol_upper = ticker_symbol.upper()
    if symbol_upper in STOCK_NAME_ZH:
        return STOCK_NAME_ZH[symbol_upper]
    return info.get("shortName") or info.get("longName") or ticker_symbol


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
        response = requests.post(url, json=payload, timeout=15)
        res_data = response.json()
        if res_data.get("ok"):
            print("✅ Telegram 彙整報告發送成功！")
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
    """估值運算核心 (優化後的機構估值模型)"""
    stock = yf.Ticker(ticker_symbol)
    info = stock.info

    current_price = get_accurate_price(stock)
    if not current_price or current_price == 0:
        raise ValueError(f"無法取得 {ticker_symbol} 即時股價。")

    stock_name = get_display_name(ticker_symbol, info)
    currency_symbol = "$" if info.get("currency") == "USD" else "NT$"
    eps_val, eps_type = get_validated_eps(stock, current_price)
    bvps = info.get("bookValue", 0.0) or 0.0
    pe_ratio = (
        (current_price / eps_val) if eps_val > 0 else info.get("trailingPE", 0.0)
    )
    pb_ratio = (current_price / bvps) if bvps > 0 else 0.0

    sector_type = get_sector_type(ticker_symbol)

    report_lines = [
        f"📌 **{stock_name}** (`{ticker_symbol}`)",
        f"💵 **當前股價**：`{currency_symbol}{current_price:.2f}`",
    ]

    # A: IC 設計 (改採動態 P/E Band 模型)
    if sector_type == "IC_DESIGN":
        # 給予 AI 旗艦龍頭較高評級，一般 IC 設計給予常態評級
        target_pe = (
            30.0 if ticker_symbol in ["NVDA", "AVGO", "AMD"] else 22.0
        )
        fair_price_pe = eps_val * target_pe
        discount_price = fair_price_pe * 0.85

        report_lines.extend(
            [
                f"• EPS ({eps_type})：`{currency_symbol}{eps_val:.2f}` | 當前 P/E：`{pe_ratio:.1f}x`",
                f"• **合理價 ({target_pe:.0f}x P/E)**：`{currency_symbol}{fair_price_pe:.2f}`",
                f"• **安全邊際 (85折)**：`{currency_symbol}{discount_price:.2f}`",
                f"💡 *訊號*：{'🟢 低於安全邊際' if current_price <= discount_price else ('🔵 處於合理估值區' if current_price <= fair_price_pe else '🟡 偏向樂觀估值區')}",
            ]
        )

    # B: 晶圓代工 / 封測重資產 (調升 EV/EBITDA 目標倍數)
    elif sector_type == "FOUNDRY_CAPEX":
        ev_ebitda = info.get("enterpriseToEbitda", 0.0) or 0.0
        # 台積電享先進製程溢價給予 18x，日月光等封測龍頭給予 14x
        target_ev_ebitda = 18.0 if ticker_symbol == "2330.TW" else 14.0
        fair_price_ev = (
            current_price * (target_ev_ebitda / ev_ebitda)
            if ev_ebitda > 0
            else current_price
        )
        discount_price = fair_price_ev * 0.85

        report_lines.extend(
            [
                f"• EV/EBITDA：`{ev_ebitda:.2f}x`",
                f"• **合理價 ({target_ev_ebitda:.1f}x EV/EBITDA)**：`{currency_symbol}{fair_price_ev:.2f}`",
                f"• **安全邊際 (85折)**：`{currency_symbol}{discount_price:.2f}`",
                f"💡 *訊號*：{'🟢 估值低於安全邊際' if current_price <= discount_price else ('🔵 處於合理估值區' if current_price <= fair_price_ev else '🟡 估值偏高')}",
            ]
        )

    # C: AI 記憶體 / HBM (維持高成長 P/E 區間)
    elif sector_type == "AI_MEMORY_HBM":
        low_pe, fair_pe, high_pe = 18.0, 22.0, 28.0
        bull_target_price = eps_val * high_pe
        fair_price = eps_val * fair_pe
        buy_target_price = eps_val * low_pe

        status = (
            "🟢 低檔建倉區"
            if current_price <= buy_target_price
            else (
                "🔵 合理估值區"
                if current_price <= fair_price
                else (
                    "🟡 已反映樂觀預期"
                    if current_price <= bull_target_price
                    else "🔴 高於樂觀目標"
                )
            )
        )

        report_lines.extend(
            [
                f"• EPS：`{currency_symbol}{eps_val:.2f}` | 當前 P/E：`{pe_ratio:.1f}x`",
                f"• **低檔價 (18x)**：`{currency_symbol}{buy_target_price:.2f}` | **合理價 (22x)**：`{currency_symbol}{fair_price:.2f}`",
                f"• **樂觀價 (28x)**：`{currency_symbol}{bull_target_price:.2f}`",
                f"💡 *訊號*：{status}",
            ]
        )

    # D: 傳統記憶體 (調升 P/B 景氣循環倍數)
    elif sector_type == "MEMORY_CYCLE":
        low_pb, fair_pb, high_pb = 1.5, 2.2, 3.2
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb

        report_lines.extend(
            [
                f"• BVPS：`{currency_symbol}{bvps:.2f}` | 當前 P/B：`{pb_ratio:.2f}x`",
                f"• **谷底買點 (P/B {low_pb}x)**：`{currency_symbol}{buy_target_price:.2f}`",
                f"• **合理價值 (P/B {fair_pb}x)**：`{currency_symbol}{fair_price:.2f}`",
                f"💡 *訊號*：{'🟢 景氣谷底區' if pb_ratio <= low_pb else ('🔴 景氣高點區' if pb_ratio >= high_pb else '🟡 週期中段/熱絡區')}",
            ]
        )

    # E: 一般通用模型
    else:
        fair_price = eps_val * 20.0
        report_lines.extend(
            [
                f"• P/E：`{pe_ratio:.1f}x` | P/B：`{pb_ratio:.2f}x`",
                f"• **20倍 P/E 基底合理價**：`{currency_symbol}{fair_price:.2f}`",
                f"💡 *訊號*：{'🟢 股價偏低' if current_price < fair_price else '🟡 股價平實'}",
            ]
        )

    return "\n".join(report_lines)


def run_job():
    """執行評估並整合成 1 封總報推播至 Telegram"""
    print(f"🚀 開始評估前 {len(TOP_10_TICKERS)} 大台美半導體龍頭標的...\n")

    reports = ["🤖 *【台美半導體前十大龍頭估值日報】*\n"]

    for ticker in TOP_10_TICKERS:
        try:
            report = evaluate_stock(ticker)
            reports.append(report)
        except Exception as e:
            print(f"⚠️ 跳過 {ticker}: {e}")

    # 以分隔線組合為一封整潔的 Telegram 訊息
    full_message = "\n\n----------------------------------\n\n".join(reports)

    print(full_message)
    print("\n" + "=" * 40 + "\n")

    send_telegram_message(full_message)


if __name__ == "__main__":
    run_job()
