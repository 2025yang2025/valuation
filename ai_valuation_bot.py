import os
import time
import numpy as np
import pandas as pd
import requests

# ==============================================================================
# 💬 Telegram 發送模組
# ==============================================================================
def send_telegram_message(message, max_length=3500):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("⚠️ 未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，無法發送 Telegram 訊息。")
        return
    
    bot_token = str(bot_token).strip()
    chat_id = str(chat_id).strip()
    if bot_token.lower().startswith("bot"):
        bot_token = bot_token[3:]

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    lines = message.split("\n")
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    if current_chunk:
        chunks.append(current_chunk)

    for idx, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
        try:
            res = requests.post(url, json=payload, timeout=10)
            print(f"📢 TG 發送狀態碼 ({idx+1}/{len(chunks)}): {res.status_code}")
        except Exception as e:
            print(f"❌ Telegram 發送異常: {e}")
        time.sleep(0.5)

# ==============================================================================
# 🎯 台美半導體估值 Pro 核心引擎
# ==============================================================================
SECTOR_CONFIG = {
    "GROWTH_AI": {
        "name": "AI/高成長股 (如 NVDA, AMD, 世芯)",
        "is_cyclical": False
    },
    "CYCLICAL_MEM": {
        "name": "記憶體/景氣循環股 (如 MU, 南亞科)",
        "is_cyclical": True
    },
    "CAPEX_FOUNDRY": {
        "name": "晶圓代工/資本密集 (如 TSMC)",
        "is_cyclical": False
    },
    "MATURE_CASH": {
        "name": "成熟/高現金流/平台 (如 AVGO, QCOM)",
        "is_cyclical": False
    },
    "ADVANCED_OSAT": {
        "name": "先進封測 (如 日月光)",
        "is_cyclical": True
    }
}

class SemiconductorValuationPro:
    def __init__(self, ticker, name, current_price, sector_type="GROWTH_AI"):
        self.ticker = ticker
        self.name = name
        self.price = current_price
        self.sector_type = sector_type
        self.config = SECTOR_CONFIG.get(sector_type, SECTOR_CONFIG["GROWTH_AI"])
        
    def calculate_and_send(
        self, 
        ttm_eps, fwd_eps, fwd_pe, cagr, fcf_yield, roe, ev_ebitda,
        hist_pe_percentile, peer_pe, bvps=0, norm_eps=0, send_tg=True
    ):
        """ 計算估值並發送至 Telegram """
        # 1. 基本指標計算
        peg = round(fwd_pe / cagr, 2) if cagr > 0 else 99.0
        effective_eps = norm_eps if (self.config["is_cyclical"] and norm_eps > 0) else fwd_eps

        # 2. 動態設定合理 PE 區間
        if cagr >= 30:
            fair_pe_min, fair_pe_max = 30.0, 40.0
        elif cagr >= 20:
            fair_pe_min, fair_pe_max = 24.0, 32.0
        elif cagr >= 10:
            fair_pe_min, fair_pe_max = 18.0, 25.0
        else:
            fair_pe_min, fair_pe_max = 12.0, 18.0

        if peer_pe > 0:
            fair_pe_min = round((fair_pe_min * 0.7 + peer_pe * 0.3), 1)
            fair_pe_max = round((fair_pe_max * 0.7 + peer_pe * 0.3), 1)

        # 3. 價格區間計算
        pe_conservative = effective_eps * fair_pe_min
        pe_fair = effective_eps * ((fair_pe_min + fair_pe_max) / 2)
        pe_optimistic = effective_eps * fair_pe_max

        if self.config["is_cyclical"] and bvps > 0:
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

        # 4. 判定評級
        if self.price <= safety_buy_price:
            rating = "🟢 價值低估"
        elif self.price <= conservative_price:
            rating = "🟢 合理偏低"
        elif self.price <= fair_price:
            rating = "🔵 合理"
        elif self.price <= optimistic_price:
            rating = "🟡 偏貴"
        elif self.price <= optimistic_price * 1.15:
            rating = "🟠 高估"
        else:
            rating = "🔴 極度高估"

        cyclical_warning = "\n⚠️ <i>[景氣循環修正] 採用平準化 EPS/PB 評估</i>" if self.config["is_cyclical"] else ""
        
        # 5. 組裝 Telegram HTML 格式
        report = f"""💎 <b>【台美半導體估值 Pro】{self.ticker} ({self.name})</b>
🏷️ <i>分類：{self.config['name']}</i>

💵 <b>當前股價：</b> {self.price}

📊 <b>基本面與估值指標</b>
• TTM EPS：{ttm_eps}
• Forward EPS：{fwd_eps} (平準化EPS: {norm_eps if norm_eps else 'N/A'})
• Forward PE：{fwd_pe}x
• EPS CAGR (3-5年)：{cagr}%
• PEG：{peg}
• FCF Yield：{fcf_yield}%
• ROE：{roe}%
• EV/EBITDA：{ev_ebitda}x
• 歷史 PE 分位：{hist_pe_percentile}%
• 同業平均 PE：{peer_pe}x

🎯 <b>多軌估值模型計算結果</b>
• 合理 PE 區間：{fair_pe_min}x ~ {fair_pe_max}x
• 保守價：{conservative_price}
• 合理價：{fair_price}
• 樂觀價：{optimistic_price}
• 🛡️ <b>安全買點：</b> {safety_buy_price}{cyclical_warning}
───────────────────
🏆 <b>最終評級：{rating}</b>"""

        print(report)

        # 6. 發送至 Telegram
        if send_tg:
            send_telegram_message(report)

        return report

# ==============================================================================
# 🚀 執行發送範例
# ==============================================================================
if __name__ == "__main__":
    # 範例 1: 台積電 2330.TW
    tsmc = SemiconductorValuationPro("2330.TW", "台積電", current_price=980.0, sector_type="CAPEX_FOUNDRY")
    tsmc.calculate_and_send(
        ttm_eps=38.5, fwd_eps=48.0, fwd_pe=20.4, cagr=22.0, 
        fcf_yield=3.8, roe=28.5, ev_ebitda=12.5, hist_pe_percentile=45.0, peer_pe=25.0,
        send_tg=True
    )

    # 範例 2: 美光 MU
    mu = SemiconductorValuationPro("MU", "美光", current_price=105.0, sector_type="CYCLICAL_MEM")
    mu.calculate_and_send(
        ttm_eps=8.5, fwd_eps=12.0, fwd_pe=8.75, cagr=15.0, 
        fcf_yield=4.5, roe=22.0, ev_ebitda=9.0, hist_pe_percentile=75.0, peer_pe=12.0,
        bvps=45.0, norm_eps=5.5, send_tg=True
    )
