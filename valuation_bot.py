import os
import requests

# 取得環境變數（從 GitHub Secrets 傳入）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

def calculate_valuation(ticker, current_price, eps_ttm, expected_growth, fcf, shares):
    """
    估值運算邏輯 (可根據產業調整)
    """
    # 1. PE & PEG 估值
    fair_pe = expected_growth * 100  # PEG = 1 假定
    pe_target_price = eps_ttm * fair_pe
    
    # 2. 簡化版 DCF 估值 (假設 5年成長率, WACC=9%, 永續成長率=2.5%)
    wacc = 0.09
    g_p = 0.025
    discounted_fcf_sum = 0
    
    # 前 5 年 FCF 現值
    curr_fcf = fcf
    for t in range(1, 6):
        curr_fcf *= (1 + expected_growth)
        discounted_fcf_sum += curr_fcf / ((1 + wacc) ** t)
        
    # 終值現值
    tv = (curr_fcf * (1 + g_p)) / (wacc - g_p)
    tv_pv = tv / ((1 + wacc) ** 5)
    
    equity_value = discounted_fcf_sum + tv_pv
    dcf_target_price = equity_value / shares

    # 安全邊際價 (8折)
    dcf_margin_of_safety = dcf_target_price * 0.8

    # 組合 Telegram Markdown 報告
    report = f"""
🤖 *【個股未來估值監控報告】*
📌 **標的：{ticker}**
----------------------------------
*當前股價*：`${current_price:.2f}`

📊 *相對估值法 (PEG)*
• 預估近四季 EPS：`${eps_ttm:.2f}`
• 預估成長率：`{expected_growth*100:.1f}%`
• PEG=1 合理目標價：`${pe_target_price:.2f}`

💰 *絕對估值法 (DCF)*
• DCF 內在價值：`${dcf_target_price:.2f}`
• **安全邊際買進價 (8折)**：`${dcf_margin_of_safety:.2f}`

💡 *綜合評估*：
{"🟢 當前股價低於安全邊際，具具備較高安全邊際！" if current_price <= dcf_margin_of_safety else "🟡 當前股價高於安全邊際，建議持續觀察。"}
"""
    return report

if __name__ == "__main__":
    # 範例數據 (實際應用中可透過 API 如 FinMind / Yahoo Finance 取得)
    report = calculate_valuation(
        ticker="2330.TW",
        current_price=980.0,
        eps_ttm=42.0,
        expected_growth=0.18, # 18% 預期成長率
        fcf=600000000000,    # FCF (NTD)
        shares=25930000000   # 股數
    )
    send_telegram_message(report)
