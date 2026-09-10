import os
import requests
import yfinance as yf

# 1. 讀取 GitHub Secrets 環境變數
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_message(message):
    """發送訊息至 Telegram 並印出詳細狀態"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 未偵測到 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，僅於 Terminal 印出：\n")
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
                f"❌ Telegram API 拒絕請求 [{response.status_code}]: {res_data.get('description')}"
            )
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
        print(
            f"⚠️ 股價數據異常錯位 (Info: {price}, K線: {hist_price})，已修正採用 K線價格。"
        )
        return hist_price

    return price


def get_validated_eps(stock, current_price):
    """EPS 雙重檢測護欄：防止 yfinance 抓到暴增的錯誤預估 EPS (如 $155.03)"""
    info = stock.info
    forward_eps = info.get("forwardEps", 0.0) or 0.0
    trailing_eps = info.get("trailingEps", 0.0) or 0.0

    # 防呆機制：若 Forward EPS 計算出的 Forward PE < 3.0x，或是 EPS > 現價的 12%，代表數據嚴重錯位
    if forward_eps > 0 and (
        current_price / forward_eps < 3.0 or forward_eps > current_price * 0.12
    ):
        print(
            f"⚠️ 偵測到極端異常 Forward EPS (${forward_eps:.2f})，自動降級採用 Trailing EPS 或校正值。"
        )
        if trailing_eps > 0 and (current_price / trailing_eps >= 5.0):
            return trailing_eps, "Trailing EPS"
        else:
            corrected_eps = current_price / 22.0  # 以市場平均 22x P/E 校正基準 EPS
            return corrected_eps, "系統校正預估 EPS"

    return forward_eps, "Forward EPS"


def generate_valuation_report(ticker_symbol, sector_category):
    stock = yf.Ticker(ticker_symbol)
    info = stock.info

    current_price = get_accurate_price(stock)
    if not current_price or current_price == 0:
        raise ValueError(f"無法取得 {ticker_symbol} 即時股價。")

    bvps = info.get("bookValue", 0.0) or 0.0
    valid_eps, eps_type = get_validated_eps(stock, current_price)

    pb_ratio = (current_price / bvps) if bvps > 0 else 0.0
    currency_symbol = "$" if info.get("currency") == "USD" else "NT$"
    stock_name = info.get("shortName", ticker_symbol)

    report_lines = [
        "🤖 *【AI 半導體自動估值日報】*",
        f"🌐 **市場**：{'🇺🇸 美股' if currency_symbol == '$' else '🇹🇼 台股'}",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name})",
        f"🏷️ **族群**：HBM / 記憶體",
        f"💵 **當前股價**：`{currency_symbol}{current_price:.2f}`",
        "----------------------------------",
    ]

    # 記憶體族群估值邏輯
    if sector_category == "AI_MEMORY_HBM":
        if pb_ratio > 3.0 and valid_eps > 0:
            low_pe, fair_pe, high_pe = 15.0, 20.0, 25.0

            bull_target_price = valid_eps * high_pe
            fair_price = valid_eps * fair_pe
            buy_target_price = valid_eps * low_pe
            current_pe = current_price / valid_eps

            model_desc = f"HBM P/E 高成長估值模型 ({eps_type})"

            if current_price <= buy_target_price:
                status = "🟢 估值處於低檔建倉區，具備安全邊際。"
            elif current_price <= fair_price:
                status = "🔵 股價處於合理估值區間。"
            elif current_price <= bull_target_price:
                status = "🟡 股價已反映樂觀獲利預期。"
            else:
                status = "🔴 股價高於樂觀預估目標，留意追高風險。"

            report_lines.extend(
                [
                    f"📊 *估值模型*：`{model_desc}`",
                    f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
                    f"• 採計 EPS ({eps_type})：`{currency_symbol}{valid_eps:.2f}` | 目前 P/E：`{current_pe:.2f}x`",
                    f"• 🎯 **樂觀目標 (P/E {high_pe:.0f}x)**：`{currency_symbol}{bull_target_price:.2f}`",
                    f"• ⚖️ **合理價值 (P/E {fair_pe:.0f}x)**：`{currency_symbol}{fair_price:.2f}`",
                    f"• 💰 **低檔買點 (P/E {low_pe:.0f}x)**：`{currency_symbol}{buy_target_price:.2f}`",
                    f"\n💡 *綜合評估*：{status}",
                ]
            )

    return "\n".join(report_lines)


def run_job():
    """執行評估任務並推播至 Telegram"""
    targets = [{"ticker": "MU", "category": "AI_MEMORY_HBM"}]

    for target in targets:
        try:
            report = generate_valuation_report(
                target["ticker"], target["category"]
            )
            print(report)
            print("\n" + "=" * 40 + "\n")
            # 發送訊息至 Telegram
            send_telegram_message(report)
        except Exception as e:
            print(f"❌ 處理 {target['ticker']} 時發生錯誤: {e}")


if __name__ == "__main__":
    run_job()
