import yfinance as yf

def get_accurate_price(stock):
    """
    雙重校驗以取得真實即時股價
    新增防呆護欄：當 info 傳回的價格與近 5 日 K 線最新收盤價偏差超過 30% 時，
    判定為 API 數據錯位，強制採用 K 線數據。
    """
    info = stock.info
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    
    # 抓取 K 線作為基準校驗
    hist = stock.history(period="5d")
    hist_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
    
    # 若 info 沒有價格，採用 K 線收盤價
    if not price or price <= 0:
        return hist_price
        
    # 防呆護欄：極端異常值過濾 (極限偏差 > 30%)
    if hist_price and (abs(price - hist_price) / hist_price > 0.30):
        print(f"⚠️ 偵測到股價數據異常錯位 (Info: {price}, K線: {hist_price})，已自動修復採用 K線價格。")
        return hist_price
            
    return price


def generate_valuation_report(ticker_symbol, sector_category):
    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    
    # 取得準確股價
    current_price = get_accurate_price(stock)
    
    # 基本財務指標
    bvps = info.get("bookValue", 0.0)
    forward_eps = info.get("forwardEps", 0.0)
    
    pb_ratio = (current_price / bvps) if bvps > 0 else 0.0
    currency_symbol = "$" if info.get("currency") == "USD" else "NT$"
    
    report_lines = [
        "🤖 【AI 半導體自動估值日報】",
        f"🌐 市場：{'🇺🇸 美股' if currency_symbol == '$' else '🇹🇼 台股'}",
        f"📌 標的：{ticker_symbol} ({info.get('shortName', 'N/A')})",
        f"🏷️ 族群：HBM / 記憶體",
        f"💵 當前股價：{currency_symbol}{current_price:.2f}",
        "----------------------------------"
    ]
    
    # --------------------------------------------------------------------------
    # 記憶體族群估值邏輯 (自動判定：傳統 P/B 週期 vs HBM 高成長 P/E)
    # --------------------------------------------------------------------------
    if sector_category == "AI_MEMORY_HBM":
        # 當 P/B 大於 3.0x 且具有高 Forward EPS 時，代表進入 HBM 高毛利轉型期，自動切換至 P/E 盈餘驅動模型
        if pb_ratio > 3.0 and forward_eps and forward_eps > 0:
            low_pe, fair_pe, high_pe = 15.0, 20.0, 25.0
            
            bull_target_price = forward_eps * high_pe
            fair_price = forward_eps * fair_pe
            buy_target_price = forward_eps * low_pe
            current_pe = current_price / forward_eps
            
            model_desc = f"HBM Forward P/E 高成長估值模型 (PE 範疇: {low_pe:.0f}x - {high_pe:.0f}x)"
            
            if current_price <= buy_target_price:
                status = "🟢 估值處於低檔建倉區，具備安全邊際。"
            elif current_price <= fair_price:
                status = "🔵 股價處於合理估值區間。"
            elif current_price <= bull_target_price:
                status = "🟡 股價已反映樂觀獲利預期。"
            else:
                status = "🔴 股價高於樂觀預估目標，留意追高風險。"

            report_lines.extend([
                f"📊 估值模型：`{model_desc}`",
                f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
                f"• 未來 12M 預估 EPS：`{currency_symbol}{forward_eps:.2f}` | 目前 Forward P/E：`{current_pe:.2f}x`",
                f"• 🎯 **樂觀目標 (P/E {high_pe:.0f}x)**：`{currency_symbol}{bull_target_price:.2f}`",
                f"• ⚖️ **合理價值 (P/E {fair_pe:.0f}x)**：`{currency_symbol}{fair_price:.2f}`",
                f"• 💰 **低檔買點 (P/E {low_pe:.0f}x)**：`{currency_symbol}{buy_target_price:.2f}`",
                f"\n💡 綜合評估：{status}"
            ])
            
        else:
            # 傳統記憶體大宗商品 P/B 週期估值邏輯
            low_pb, fair_pb, high_pb = 1.2, 1.8, 2.3
            
            bull_target_price = bvps * high_pb
            fair_price = bvps * fair_pb
            buy_target_price = bvps * low_pb
            
            model_desc = f"P/B 淨值比週期模型 (PB 範疇: {low_pb}x - {high_pb}x)"
            
            if pb_ratio <= low_pb:
                status = "🟢 進入 P/B 週期低估建倉區！"
            elif pb_ratio <= fair_pb:
                status = "🔵 股價處於週期合理區間。"
            else:
                status = "🟡 注意景氣擴產週期與高檔拉回風險。"

            report_lines.extend([
                f"📊 估值模型：`{model_desc}`",
                f"• 每股淨值 (BVPS)：`{currency_symbol}{bvps:.2f}` | 目前 P/B：`{pb_ratio:.2f}x`",
                f"• 🎯 **景氣高檔目標 (P/B {high_pb}x)**：`{currency_symbol}{bull_target_price:.2f}`",
                f"• ⚖️ **合理價值區間 (P/B {fair_pb}x)**：`{currency_symbol}{fair_price:.2f}`",
                f"• 💰 **週期低檔買點 (P/B {low_pb}x)**：`{currency_symbol}{buy_target_price:.2f}`",
                f"\n💡 綜合評估：{status}"
            ])

    return "\n".join(report_lines)

# 測試輸出
if __name__ == "__main__":
    print(generate_valuation_report("MU", "AI_MEMORY_HBM"))
