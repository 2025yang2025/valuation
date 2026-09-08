import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. AI 半導體供應鏈監控清單 (含市場標示與精準中文名稱)
AI_SEMICON_SECTORS = {
    # A. AI 晶片 / IP / 客製化晶片 ASIC (適用 P/E & PEG 成長模型)
    "AI_CHIP_DESIGN": {
        "name_zh": "AI晶片 / IP / ASIC",
        "stocks": [
            {"ticker": "NVDA", "name": "輝達", "market": "US"},
            {"ticker": "AMD", "name": "超微", "market": "US"},
            {"ticker": "AVGO", "name": "博通", "market": "US"},
            {"ticker": "2454.TW", "name": "聯發科", "market": "TW"},
            {"ticker": "3661.TW", "name": "世芯-KY", "market": "TW"},
            {"ticker": "3443.TW", "name": "創意", "market": "TW"},
            {"ticker": "6643.TWO", "name": "M31", "market": "TW"},
            {"ticker": "3035.TW", "name": "智原", "market": "TW"}
        ]
    },
    # B. 先進製程晶圓代工 / 先進封裝 CoWoS / 設備 (適用 EV/EBITDA 模型)
    "AI_FOUNDRY_COWOS": {
        "name_zh": "晶圓代工 / CoWoS / 設備",
        "stocks": [
            {"ticker": "TSM", "name": "台積電 ADR", "market": "US"},
            {"ticker": "2330.TW", "name": "台積電", "market": "TW"},
            {"ticker": "3711.TW", "name": "日月光投控", "market": "TW"},
            {"ticker": "ASML", "name": "艾司摩爾", "market": "US"},
            {"ticker": "AMAT", "name": "應用材料", "market": "US"}
        ]
    },
    # C. HBM 高頻寬記憶體 / 記憶體 (適用 P/B 週期模型)
    "AI_MEMORY_HBM": {
        "name_zh": "HBM / 記憶體",
        "stocks": [
            {"ticker": "MU", "name": "美光", "market": "US"},
            {"ticker": "2408.TW", "name": "南亞科", "market": "TW"}
        ]
    },
    # D. AI 伺服器代工 / 組裝 (適用 P/E 傳統估值 + 轉型溢價)
    "AI_SERVER_OEM": {
        "name_zh": "AI 伺服器組裝",
        "stocks": [
            {"ticker": "2317.TW", "name": "鴻海", "market": "TW"},
            {"ticker": "2382.TW", "name": "廣達", "market": "TW"},
            {"ticker": "3231.TW", "name": "緯創", "market": "TW"},
            {"ticker": "6669.TW", "name": "緯穎", "market": "TW"},
            {"ticker": "SMCI", "name": "美超微", "market": "US"}
        ]
    }
}

def send_telegram_message(message):
    """發送訊息至 Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("未設定 Telegram Token 或 Chat ID，僅於 Terminal 印出：\n", message)
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
            print(f"❌ Telegram 發送失敗 [{response.status_code}]: {res_data.get('description')}")
    except Exception as e:
        print(f"❌ 發送連線失敗: {e}")

def evaluate_ai_stock(stock_info, sector_category):
    """計算估值報告"""
    ticker_symbol = stock_info["ticker"]
    stock_name_zh = stock_info["name"]
    market_flag = "🇹🇼 台股" if stock_info["market"] == "TW" else "🇺🇸 美股"
    currency_symbol = "NT$" if stock_info["market"] == "TW" else "$"

    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not current_price or current_price == 0:
        raise ValueError(f"Yahoo Finance 無法取得 `{ticker_symbol}` 報價數據。")
        
    eps_ttm = info.get("trailingEps", 0) or 0.0
    bvps = info.get("bookValue", 0) or 0.0
    pe_ratio = info.get("trailingPE", 0) or 0.0
    pb_ratio = info.get("priceToBook", 0) or 0.0
    
    report_lines = [
        f"🤖 *【AI 半導體自動估值日報】*",
        f"🌐 **市場**：`{market_flag}`",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name_zh})",
        f"🏷️ **族群**：`{AI_SEMICON_SECTORS[sector_category]['name_zh']}`",
        f"💵 **當前股價**：`{currency_symbol}{current_price:.2f}`",
        f"----------------------------------"
    ]
    
    # 邏輯 A: IC 設計 / IP (PEG 模型 + 負數/低成長率防護)
    if sector_category == "AI_CHIP_DESIGN":
        raw_growth = info.get("earningsGrowth", 0.15) or 0.15
        # 防護：若成長率 <= 5% (含負值)，自動保底採用 15.0%
        if raw_growth <= 0.05:
            growth_for_peg = 0.15
            growth_note = f"{raw_growth*100:.1f}% (採保底值 15.0%)"
        else:
            growth_for_peg = raw_growth
            growth_note = f"{growth_for_peg * 100:.1f}%"

        # 目標 P/E 限制在 12x ~ 50x 避免過度極端
        target_pe = min(max(growth_for_peg * 100, 12.0), 50.0)
        fair_price = eps_ttm * target_pe
        discount_price = fair_price * 0.8

        report_lines.extend([
            f"📊 *估值模型*：`PEG 成長模型 (高研發/輕資產)`",
            f"• 近四季 EPS：`{currency_symbol}{eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• 預估盈餘成長率：`{growth_note}`",
            f"• **PEG=1.0 合理目標價**：`{currency_symbol}{fair_price:.2f}`",
            f"• **8 折安全邊際買進價**：`{currency_symbol}{discount_price:.2f}`",
            f"\n💡 *評語*：{'🟢 當前股價已進入安全邊際區！' if current_price <= discount_price else '🟡 處於成長溢價區，留意 AI 資本支出釋出狀況。'}"
        ])

    # 邏輯 B: 晶圓代工 / 設備 (EV/EBITDA 模型 + 數據異常降級防護)
    elif sector_category == "AI_FOUNDRY_COWOS":
        ev_ebitda = info.get("enterpriseToEbitda", 0) or 0.0
        target_ev_ebitda = 15.0  # 半導體設備與先進製程合理 EV/EBITDA 約 15x
        
        # 防呆驗證：若 EV/EBITDA 數據合理 (5x ~ 50x 之間)，使用 EV/EBITDA 模型
        if 5.0 <= ev_ebitda <= 50.0:
            fair_price = current_price * (target_ev_ebitda / ev_ebitda)
            model_name = f"EV/EBITDA 模型 ({ev_ebitda:.1f}x)"
        else:
            # 數據異常 (如 ASML 單位錯位) 時，自動降級切換為 P/E 估值模型
            fair_pe = 28.0 if "ASML" in ticker_symbol else 22.0  # ASML 享有較高壟斷溢價
            fair_price = eps_ttm * fair_pe
            model_name = f"P/E 備用模型 (數據護欄啟用, 採 {fair_pe:.0f}x PE)"

        # 安全邊際價 (85折)
        discount_price = fair_price * 0.85

        report_lines.extend([
            f"📊 *估值模型*：`{model_name}`",
            f"• 近四季 EPS：`{currency_symbol}{eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• **合理目標價**：`{currency_symbol}{fair_price:.2f}`",
            f"• **85 折安全邊際買進價**：`{currency_symbol}{discount_price:.2f}`",
            f"\n💡 *評語*：{'🟢 產能滿載且估值偏低，具安全性！' if current_price <= discount_price else '🟡 先進封裝/設備需求強勁，股價已部分反應。'}"
        ])

    # 邏輯 C: 記憶體 (P/B 淨值比)
    elif sector_category == "AI_MEMORY_HBM":
        low_pb, fair_pb = 1.2, 1.8
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb

        report_lines.extend([
            f"📊 *估值模型*：`P/B 淨值比 (HBM 結構性重估)`",
            f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
            f"• **週期低檔買點 (P/B {low_pb}x)**：`{currency_symbol}{buy_target_price:.2f}`",
            f"• **合理價值區間 (P/B {fair_pb}x)**：`{currency_symbol}{fair_price:.2f}`",
            f"\n💡 *評語*：{'🟢 進入 P/B 低估建倉區！' if pb_ratio <= low_pb else '🟡 HBM 供不應求，注意景氣擴產週期。'}"
        ])

    # 邏輯 D: 伺服器代工 (P/E 評估)
    else:
        fair_pe = 16.0
        fair_price = eps_ttm * fair_pe
        discount_price = fair_price * 0.8

        report_lines.extend([
            f"📊 *估值模型*：`AI 伺服器代工 PE 模型`",
            f"• 近四季 EPS：`{currency_symbol}{eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• **合理目標價 (16.0x P/E)**：`{currency_symbol}{fair_price:.2f}`",
            f"• **8 折安全邊際買進價**：`{currency_symbol}{discount_price:.2f}`",
            f"\n💡 *評語*：{'🟢 股價低於伺服器轉型估值下限！' if current_price <= discount_price else '🟡 需觀察 AI 伺服器出貨比重與毛利率變化。'}"
        ])

    return "\n".join(report_lines)

def run_ai_valuation_job():
    """執行全自動估值評估流程"""
    for sector_key, sector_info in AI_SEMICON_SECTORS.items():
        for stock_info in sector_info["stocks"]:
            ticker = stock_info["ticker"]
            try:
                report = evaluate_ai_stock(stock_info, sector_key)
                send_telegram_message(report)
                print(f"✅ 成功發送 [{stock_info['market']}] {ticker} ({stock_info['name']}) 估值報告")
            except Exception as e:
                print(f"⚠️ 跳過 {ticker}：{e}")

if __name__ == "__main__":
    run_ai_valuation_job()
