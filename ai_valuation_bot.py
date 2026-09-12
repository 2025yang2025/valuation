import os
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf

# ==============================================================================
# 💬 Telegram 發送模組
# ==============================================================================
def send_telegram_message(message, max_length=3500):
    bot_token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not bot_token or not chat_id:
        print("⚠️ 未設定 TG_BOT_TOKEN 或 TG_CHAT_ID，跳過 Telegram 發送。")
        return
    
    bot_token = str(bot_token).strip()
    chat_id = str(chat_id).strip()
    if bot_token.lower().startswith("bot"):
        bot_token = bot_token[3:]

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"📢 TG 發送狀態碼: {res.status_code}")
    except Exception as e:
        print(f"❌ Telegram 發送異常: {e}")

# ==============================================================================
# 🎯 台美股 Top 10 熱門半導體標的與估值類別設定
# ==============================================================================
TOP10_STOCKS = {
    # 🇺🇸 美股 Top 10
    "NVDA": {"name": "英偉達", "sector": "GROWTH_AI"},
    "TSM": {"name": "台積電ADR", "sector": "CAPEX_FOUNDRY"},
    "AVGO": {"name": "博通", "sector": "MATURE_CASH"},
    "AMD": {"name": "超微", "sector": "GROWTH_AI"},
    "MU": {"name": "美光", "sector": "CYCLICAL_MEM"},
    "QCOM": {"name": "高通", "sector": "MATURE_CASH"},
    "INTC": {"name": "英特爾", "sector": "CAPEX_FOUNDRY"},
    "AMAT": {"name": "應用材料", "sector": "CAPEX_FOUNDRY"},
    "LRCX": {"name": "科林研發", "sector": "CAPEX_FOUNDRY"},
    "ARM": {"name": "安謀", "sector": "GROWTH_AI"},

    # 🇹🇼 台股 Top 10
    "2330.TW": {"name": "台積電", "sector": "CAPEX_FOUNDRY"},
    "2454.TW": {"name": "聯發科", "sector": "GROWTH_AI"},
    "3711.TW": {"name": "日月光投控", "sector": "ADVANCED_OSAT"},
    "3661.TW": {"name": "世芯-KY", "sector": "GROWTH_AI"},
    "3443.TW": {"name": "創意", "sector": "GROWTH_AI"},
    "2408.TW": {"name": "南亞科", "sector": "CYCLICAL_MEM"},
    "3034.TW": {"name": "聯詠", "sector": "MATURE_CASH"},
    "3035.TW": {"name": "智原", "sector": "GROWTH_AI"},
    "2379.TW": {"name": "瑞昱", "sector": "MATURE_CASH"},
    "6643.TW": {"name": "M31", "sector": "GROWTH_AI"}
}

SECTOR_CONFIG = {
    "GROWTH_AI": {"name": "AI/高成長股", "is_cyclical": False},
    "CYCLICAL_MEM": {"name": "記憶體/景氣循環股", "is_cyclical": True},
    "CAPEX_FOUNDRY": {"name": "晶圓代工/設備/資本密集", "is_cyclical": False},
    "MATURE_CASH": {"name": "成熟/高現金流/平台", "is_cyclical": False},
    "ADVANCED_OSAT": {"name": "先進封測", "is_cyclical": True}
}

# ==============================================================================
# 🚀 yfinance 自動抓取與多軌估值計算核心
# ==============================================================================
def process_stock_valuation(ticker, info_meta, send_tg=True):
    print(f"\n🔄 正在抓取數據並分析: {ticker} ({info_meta['name']})...")
    stock = yf.Ticker(ticker)
    info = stock.info

    # 1. 自動提取最新市場即時價格與財務數據
    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
    ttm_eps = info.get("trailingEps") or 0.0
    fwd_eps = info.get("forwardEps") or ttm_eps
    fwd_pe = info.get("forwardPE") or (current_price / fwd_eps if fwd_eps > 0 else 0.0)
    cagr = round((info.get("earningsGrowth", 0.15) or 0.15) * 100, 1) # 預設/抓取 CAGR
    roe = round((info.get("returnOnEquity", 0.15) or 0.15) * 100, 1)
    ev_ebitda = round(info.get("enterpriseToEbitda", 15.0) or 15.0, 1)
    bvps = info.get("bookValue") or 0.0
    fcf_yield = round(((info.get("freeCashflow", 0) or 0) / (info.get("marketCap", 1) or 1)) * 100, 1)
    peer_pe = round(info.get("pegRatio", 1.0) * cagr, 1) if info.get("pegRatio") else 22.0

    if current_price == 0.0:
        print(f"❌ 抓取 {ticker} 價格失敗，跳過。")
        return None

    # 2. 確定產業配置
    sector_type = info_meta["sector"]
    config = SECTOR_CONFIG.get(sector_type, SECTOR_CONFIG["GROWTH_AI"])

    # 針對景氣循環股 (如 MU, 南亞科) 處理平準化 EPS
    norm_eps = round(ttm_eps * 0.8, 2) if config["is_cyclical"] else fwd_eps
    effective_eps = norm_eps if config["is_cyclical"] else fwd_eps

    # 3. 動態設定合理 PE 區間
    if cagr >= 25:
        fair_pe_min, fair_pe_max = 28.0, 38.0
    elif cagr >= 15:
        fair_pe_min, fair_pe_max = 20.0, 28.0
    elif cagr >= 8:
        fair_pe_min, fair_pe_max = 15.0, 22.0
    else:
        fair_pe_min, fair_pe_max = 10.0, 16.0

    # 4. 多軌算出價格區間 (保守 / 合理 / 樂觀)
    pe_conservative = effective_eps * fair_pe_min
    pe_fair = effective_eps * ((fair_pe_min + fair_pe_max) / 2)
    pe_optimistic = effective_eps * fair_pe_max

    if config["is_cyclical"] and bvps > 0:
        fair_pb = max(1.0, round(roe / 6.0, 2))
        pb_fair = bvps * fair_pb
        pb_conservative = pb_fair * 0.85
        pb_optimistic = pb_fair * 1.25
        
        conservative_price = round(pe_conservative * 0.5 + pb_conservative * 0.5, 1)
        fair_price = round(pe_fair * 0.5 + pb_fair * 0.5, 1)
        optimistic_price = round(pe_optimistic * 0.5 + pb_optimistic * 0.5, 1)
    else:
        conservative_price = round(pe_conservative, 1)
        fair_price = round(pe_fair, 1)
        optimistic_price = round(pe_optimistic, 1)

    safety_buy_price = round(conservative_price * 0.9, 1)

    # 5. 判定評級
    if current_price <= safety_buy_price:
        rating = "🟢 價值低估"
    elif current_price <= conservative_price:
        rating = "🟢 合理偏低"
    elif current_price <= fair_price:
        rating = "🔵 合理"
    elif current_price <= optimistic_price:
        rating = "🟡 偏貴"
    elif current_price <= optimistic_price * 1.15:
        rating = "🟠 高估"
    else:
        rating = "🔴 極度高估"

    peg = round(fwd_pe / cagr, 2) if cagr > 0 else 99.0
    cyclical_warning = "\n⚠️ <i>[景氣循環修正] 採用平準化 EPS/PB 評估</i>" if config["is_cyclical"] else ""

    # 6. 組裝 Telegram HTML 格式
    report = f"""💎 <b>【台美半導體估值 Pro】{ticker} ({info_meta['name']})</b>
🏷️ <i>分類：{config['name']}</i>

💵 <b>當前即時股價：</b> {current_price}

📊 <b>基本面與估值指標</b>
• TTM EPS：{ttm_eps}
• Forward EPS：{fwd_eps}
• Forward PE：{round(fwd_pe, 1)}x
• EPS CAGR (預估)：{cagr}%
• PEG：{peg}
• FCF Yield：{fcf_yield}%
• ROE：{roe}%
• EV/EBITDA：{ev_ebitda}x

🎯 <b>多軌估值模型計算結果</b>
• 合理 PE 區間：{fair_pe_min}x ~ {fair_pe_max}x
• 保守價：{conservative_price}
• 合理價：{fair_price}
• 樂觀價：{optimistic_price}
• 🛡️ <b>安全買點：</b> {safety_buy_price}{cyclical_warning}
───────────────────
🏆 <b>最終評級：{rating}</b>"""

    print(report)

    if send_tg:
        send_telegram_message(report)
        time.sleep(1) # 防請求過快

    return report

# ==============================================================================
# 執行全台美股 Top 10 熱門標的估值掃瞄
# ==============================================================================
if __name__ == "__main__":
    for ticker, meta in TOP10_STOCKS.items():
        try:
            process_stock_valuation(ticker, meta, send_tg=True)
        except Exception as e:
            print(f"❌ 處理 {ticker} 發生錯誤: {e}")
