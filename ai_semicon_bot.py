import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. 定義 AI 半導體供應鏈監控清單 (修正上櫃股票尾碼為 .TWO)
AI_SEMICON_SECTORS = {
    # A. AI 晶片 / IP / 客製化晶片 ASIC (適用 P/E & PEG 成長模型)
    "AI_CHIP_DESIGN": {
        "tickers": ["NVDA", "AMD", "AVGO", "2454.TW", "3661.TW", "3443.TW", "6643.TWO", "3035.TW"],
        "name_zh": "AI晶片 / IP / ASIC"
    },
    # B. 先進製程晶圓代工 / 先進封裝 CoWoS / 設備 (適用 EV/EBITDA 模型)
    "AI_FOUNDRY_COWOS": {
        "tickers": ["TSM", "2330.TW", "3711.TW", "ASML", "AMAT"],
        "name_zh": "晶圓代工 / CoWoS / 設備"
    },
    # C. HBM 高頻寬記憶體 / 記憶體 (適用 P/B 週期模型)
    "AI_MEMORY_HBM": {
        "tickers": ["MU", "2408.TW"],  # 排除可能引發格式異常的非美台股標的，確保穩定
        "name_zh": "HBM / 記憶體"
    },
    # D. AI 伺服器代工 / 組裝 (適用 P/E 傳統估值 + 伺服器營收比)
    "AI_SERVER_OEM": {
        "tickers": ["2317.TW", "2382.TW", "3231.TW", "6669.TW", "SMCI"],
        "name_zh": "AI 伺服器組裝"
    }
}

def send_telegram_message(message):
    """發送訊息至 Telegram (含詳細除錯 Log)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 未偵測到 Telegram Token 或 Chat ID Secrets！")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        res_data = response.json()
        if not res_data.get("ok"):
            print(f"❌ Telegram API 回傳錯誤 [{response.status_code}]: {res_data.get('description')}")
        else:
            print("📩 Telegram 訊息發送成功！")
    except Exception as e:
        print(f"❌ 網路連線錯誤: {e}")

def evaluate_ai_stock(ticker_symbol, sector_category):
    """根據 AI 供應鏈分工計算最適估值"""
    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    
    # 資料安全驗證：檢查是否能成功抓到價格
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not current_price or current_price == 0:
        raise ValueError(f"Yahoo Finance 找不到 `{ticker_symbol}` 的即時報價數據。")
        
    stock_name = info.get("shortName", ticker_symbol)
    eps_ttm = info.get("trailingEps", 0) or 0.0
    bvps = info.get("bookValue", 0) or 0.0
    pe_ratio = info.get("trailingPE", 0) or 0.0
    pb_ratio = info.get("priceToBook", 0) or 0.0
    earnings_growth = info.get("earningsGrowth", 0.20) or 0.20
    
    report_lines = [
        f"🤖 *【AI 半導體自動估值日報】*",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name})",
        f"🏷️ **族群**：`{AI_SEMICON_SECTORS[sector_category]['name_zh']}`",
        f"💵 **當前股價**：`${current_price:.2f}`",
        f"----------------------------------"
    ]
    
    # 估值邏輯分流
    if sector_category == "AI_CHIP_DESIGN":
        target_pe = earnings_growth * 100
        fair_price = eps_ttm * target_pe
        discount_price = fair_price * 0.8

        report_lines.extend([
            f"📊 *估值模型*：`PEG 成長模型 (高研發/輕資產)`",
            f"• 近四季 EPS：`${eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• 預估盈餘成長率：`{earnings_growth * 100:.1f}%`",
            f"• **PEG=1.0 合理目標價**：`${fair_price:.2f}`",
            f"• **8 折安全邊際買進價**：`${discount_price:.2f}`",
            f"\n💡 *評語*：{'🟢 當前股價已進入安全邊際區！' if current_price <= discount_price else '🟡 處於成長溢價區，留意 AI 資本支出釋出狀況。'}"
        ])

    elif sector_category == "AI_FOUNDRY_COWOS":
        ev_ebitda = info.get("enterpriseToEbitda", 0) or 0.0
        target_ev_ebitda = 12.0
        fair_price = current_price * (target_ev_ebitda / ev_ebitda) if ev_ebitda > 0 else current_price
        discount_price = fair_price * 0.85

        report_lines.extend([
            f"📊 *估值模型*：`EV/EBITDA 重資產還原模型`",
            f"• 當前 EV/EBITDA：`{ev_ebitda:.2f}x`",
            f"• **合理目標價 ({target_ev_ebitda:.1f}x EV/EBITDA)**：`${fair_price:.2f}`",
            f"• **85 折安全邊際買進價**：`${discount_price:.2f}`",
            f"\n💡 *評語*：{'🟢 產能滿載且估值偏低，具安全性！' if current_price <= discount_price else '🟡 先進封裝 CoWoS 產能緊繃，股價已部分反應。'}"
        ])

    elif sector_category == "AI_MEMORY_HBM":
        low_pb, fair_pb = 1.2, 1.8
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb

        report_lines.extend([
            f"📊 *估值模型*：`P/B 淨值比 (HBM 結構性重估)`",
            f"• 每股淨值 (BVPS)：`${bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
            f"• **週期低檔買點 (P/B {low_pb}x)**：`${buy_target_price:.2f}`",
            f"• **合理價值區間 (P/B {fair_pb}x)**：`${fair_price:.2f}`",
            f"\n💡 *評語*：{'🟢 進入 P/B 低估建倉區！' if pb_ratio <= low_pb else '🟡 HBM 供不應求，注意景氣擴產週期。'}"
        ])

    else: # AI_SERVER_OEM
        fair_pe = 16.0
        fair_price = eps_ttm * fair_pe
        discount_price = fair_price * 0.8

        report_lines.extend([
            f"📊 *估值模型*：`AI 伺服器代工 PE 模型`",
            f"• 近四季 EPS：`${eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• **合理目標價 (16.0x P/E)**：`${fair_price:.2f}`",
            f"• **8 折安全邊際買進價**：`${discount_price:.2f}`",
            f"\n💡 *評語*：{'🟢 股價低於伺服器轉型估值下限！' if current_price <= discount_price else '🟡 需觀察 AI 伺服器出貨比重與毛利率變化。'}"
        ])

    return "\n".join(report_lines)

def run_ai_valuation_job():
    """遍歷所有 AI 供應鏈股票並發送報告 (含容錯機制)"""
    for sector_key, sector_info in AI_SEMICON_SECTORS.items():
        for ticker in sector_info["tickers"]:
            try:
                report = evaluate_ai_stock(ticker, sector_key)
                send_telegram_message(report)
                print(f"✅ 成功計算並發送 {ticker} 估值報告")
            except Exception as e:
                # 若發生 404 或資料缺失，印出警告後自動跳過，繼續執行下一檔
                print(f"⚠️ 跳過 {ticker}：{e}")

if __name__ == "__main__":
    run_ai_valuation_job()
