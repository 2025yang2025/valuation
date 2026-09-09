import os
import requests
import yfinance as yf

# 1. 讀取環境變數 (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. AI 半導體與伺服器供應鏈監控清單
AI_SEMICON_SECTORS = {
    # A. AI 晶片 / IP / 客製化晶片 ASIC
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
    # B. 晶圓代工 / 先進封裝 CoWoS / 設備
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
    # C. HBM 高頻寬記憶體 / 記憶體
    "AI_MEMORY_HBM": {
        "name_zh": "HBM / 記憶體",
        "stocks": [
            {"ticker": "MU", "name": "美光", "market": "US"},
            {"ticker": "2408.TW", "name": "南亞科", "market": "TW"}
        ]
    },
    # D. AI 伺服器代工 / 組裝
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
        print("⚠️ 未設定 Telegram Secrets，僅於控制台印出：\n", message)
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
    except Exception as e:
        print(f"❌ 發送訊息網路連線失敗: {e}")

def get_accurate_price(stock):
    """雙重校驗以取得真實即時股價 (避免 yfinance 價格單位錯位)"""
    info = stock.info
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    
    # 若 info 抓到的價格異常或為 None，改從 K 線取最近一日收盤價
    if not price or price <= 0:
        hist = stock.history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            
    return price

def evaluate_ai_stock(stock_info, sector_category):
    """根據外資三階估值法計算 (保守 / 合理 / 樂觀目標價)"""
    ticker_symbol = stock_info["ticker"]
    stock_name_zh = stock_info["name"]
    market_flag = "🇹🇼 台股" if stock_info["market"] == "TW" else "🇺🇸 美股"
    currency_symbol = "NT$" if stock_info["market"] == "TW" else "$"

    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    
    current_price = get_accurate_price(stock)
    if not current_price or current_price == 0:
        raise ValueError(f"Yahoo Finance 無法取得 `{ticker_symbol}` 即時報價數據。")
        
    eps_ttm = info.get("trailingEps", 0) or 0.0
    bvps = info.get("bookValue", 0) or 0.0
    pe_ratio = (current_price / eps_ttm) if eps_ttm > 0 else (info.get("trailingPE", 0) or 0.0)
    pb_ratio = info.get("priceToBook", 0) or (current_price / bvps if bvps > 0 else 0.0)
    
    # 優先使用市場預估 Forward EPS，若無則透過成長率推算
    forward_eps_market = info.get("forwardEps")
    if forward_eps_market and forward_eps_market > 0:
        forward_eps = forward_eps_market
    else:
        raw_growth = info.get("earningsGrowth", 0.20) or 0.20
        growth_rate = min(max(raw_growth, 0.15), 0.50) # 防呆限制 15%~50%
        forward_eps = eps_ttm * (1 + growth_rate) if eps_ttm > 0 else current_price / 25.0

    report_lines = [
        f"🤖 *【AI 半導體自動估值日報】*",
        f"🌐 **市場**：`{market_flag}`",
        f"📌 **標的**：`{ticker_symbol}` ({stock_name_zh})",
        f"🏷️ **族群**：`{AI_SEMICON_SECTORS[sector_category]['name_zh']}`",
        f"💵 **當前股價**：`{currency_symbol}{current_price:.2f}`",
        f"----------------------------------"
    ]
    
    # --------------------------------------------------------------------------
    # 邏輯 A: IC 設計 / IP / ASIC (外資三階 Forward PE 模型)
    # --------------------------------------------------------------------------
    if sector_category == "AI_CHIP_DESIGN":
        if ticker_symbol in ["6643.TWO", "3661.TW", "3443.TW"]:
            base_pe, fair_pe, bull_pe = 25.0, 35.0, 45.0
            model_type = "純 IP / 高階 ASIC"
        elif ticker_symbol in ["2454.TW", "3035.TW"]:
            base_pe, fair_pe, bull_pe = 16.0, 20.0, 25.0
            model_type = "大型 IC 設計廠"
        else:
            base_pe, fair_pe, bull_pe = 22.0, 28.0, 35.0
            model_type = "美股 AI 晶片巨頭"

        conservative_price = forward_eps * base_pe
        fair_price = forward_eps * fair_pe
        bull_target_price = forward_eps * bull_pe
        safety_buy_price = conservative_price * 0.90

        # 位階判斷
        if current_price <= safety_buy_price:
            status = "🟢 甜甜價 (低於 9 折安全買點)"
        elif current_price <= fair_price:
            status = "🔵 合理價區間 (適合逢低佈局)"
        elif current_price <= bull_target_price:
            status = "🟡 偏向樂觀區間 (接近外資目標價)"
        else:
            status = "🔴 估值過熱 (高於外資樂觀目標價)"

        report_lines.extend([
            f"📊 *估值模型*：`外資三階 Forward PE ({model_type})`",
            f"• 未來 12M 預估 EPS：`{currency_symbol}{forward_eps:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"\n🎯 **外資估值位階**：",
            f"• 🎯 **樂觀目標價 ({bull_pe:.0f}x PE)**：`{currency_symbol}{bull_target_price:.2f}`",
            f"• ⚖️ **外資合理價 ({fair_pe:.0f}x PE)**：`{currency_symbol}{fair_price:.2f}`",
            f"• 🛡️ **保守評價價 ({base_pe:.0f}x PE)**：`{currency_symbol}{conservative_price:.2f}`",
            f"• 💰 **安全邊際價 (90 折)**：`{currency_symbol}{safety_buy_price:.2f}`",
            f"\n💡 *綜合評估*：{status}"
        ])

    # --------------------------------------------------------------------------
    # 邏輯 B: 晶圓代工 / 設備 (EV/EBITDA 或 P/E 三階護欄)
    # --------------------------------------------------------------------------
    elif sector_category == "AI_FOUNDRY_COWOS":
        ev_ebitda = info.get("enterpriseToEbitda", 0) or 0.0
        
        if 5.0 <= ev_ebitda <= 50.0:
            target_ev = 15.0
            fair_price = current_price * (target_ev / ev_ebitda)
            bull_target_price = fair_price * 1.2
            safety_buy_price = fair_price * 0.85
            model_name = f"EV/EBITDA 模型 ({ev_ebitda:.1f}x)"
        else:
            fair_pe = 28.0 if "ASML" in ticker_symbol else 22.0
            fair_price = eps_ttm * fair_pe
            bull_target_price = fair_price * 1.25
            safety_buy_price = fair_price * 0.85
            model_name = f"P/E 護欄模型 ({fair_pe:.0f}x PE)"

        if current_price <= safety_buy_price:
            status = "🟢 產能滿載且估值偏低，具安全性！"
        else:
            status = "🟡 先進封裝與設備需求強勁，股價已反應合理預期。"

        report_lines.extend([
            f"📊 *估值模型*：`{model_name}`",
            f"• 近四季 EPS：`{currency_symbol}{eps_ttm:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• 🎯 **外資樂觀目標價**：`{currency_symbol}{bull_target_price:.2f}`",
            f"• ⚖️ **合理目標價**：`{currency_symbol}{fair_price:.2f}`",
            f"• 💰 **85 折安全買進價**：`{currency_symbol}{safety_buy_price:.2f}`",
            f"\n💡 *綜合評估*：{status}"
        ])

    # --------------------------------------------------------------------------
    # 邏輯 C: 記憶體 (P/B 週期模型)
    # --------------------------------------------------------------------------
    elif sector_category == "AI_MEMORY_HBM":
        low_pb, fair_pb, high_pb = 1.2, 1.8, 2.3
        buy_target_price = bvps * low_pb
        fair_price = bvps * fair_pb
        bull_target_price = bvps * high_pb

        status = "🟢 進入 P/B 低估建倉區！" if pb_ratio <= low_pb else "🟡 HBM 供不應求，注意景氣擴產週期。"

        report_lines.extend([
            f"📊 *估值模型*：`P/B 淨值比 (HBM 週期模型)`",
            f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
            f"• 🎯 **景氣高檔目標 (P/B {high_pb}x)**：`{currency_symbol}{bull_target_price:.2f}`",
            f"• ⚖️ **合理價值區間 (P/B {fair_pb}x)**：`{currency_symbol}{fair_price:.2f}`",
            f"• 💰 **週期低檔買點 (P/B {low_pb}x)**：`{currency_symbol}{buy_target_price:.2f}`",
            f"\n💡 *綜合評估*：{status}"
        ])

    # --------------------------------------------------------------------------
    # 邏輯 D: AI 伺服器代工 (Forward PE 伺服器溢價模型)
    # --------------------------------------------------------------------------
    else:
        base_pe, fair_pe, bull_pe = 14.0, 18.0, 22.0
        conservative_price = forward_eps * base_pe
        fair_price = forward_eps * fair_pe
        bull_target_price = forward_eps * bull_pe
        safety_buy_price = conservative_price * 0.90

        if current_price <= safety_buy_price:
            status = "🟢 股價低於伺服器轉型估值下限！"
        else:
            status = "🟡 需觀察 AI 伺服器出貨比重與毛利率變化。"

        report_lines.extend([
            f"📊 *估值模型*：`AI 伺服器 Forward PE 模型`",
            f"• 未來 12M 預估 EPS：`{currency_symbol}{forward_eps:.2f}` | 目前 P/E：`{pe_ratio:.1f}x`",
            f"• 🎯 **外資樂觀目標價 ({bull_pe:.0f}x PE)**：`{currency_symbol}{bull_target_price:.2f}`",
            f"• ⚖️ **外資合理價 ({fair_pe:.0f}x PE)**：`{currency_symbol}{fair_price:.2f}`",
            f"• 💰 **安全邊際價 (90 折)**：`{currency_symbol}{safety_buy_price:.2f}`",
            f"\n💡 *綜合評估*：{status}"
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
                print(f"✅ 成功計算並發送 [{stock_info['market']}] {ticker} ({stock_info['name']}) 估值報告")
            except Exception as e:
                print(f"⚠️ 跳過 {ticker}：{e}")

if __name__ == "__main__":
    run_ai_valuation_job()
