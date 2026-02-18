import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 1. CONFIGURATION ---
FAMILY_PORTFOLIOS = {
    "มินทร์": {
        "currency": "USD",
        "assets": {
            "SCHD": 0.40,
            "MSFT": 0.30,
            "AVGO": 0.30
        }
    },
    "ฟิวส์": {
        "currency": "USD",
        "assets": {
            "VOO": 0.50,
            "QQQ": 0.30,
            "VNM": 0.20
        }
    },
    "คุณพ่อ 🛡️ (Safe Haven)": {
        "currency": "USD",
        "assets": {
            "VOO": 0.60,
            "BRK-B": 0.40
        }
    }
}

# --- 2. HELPER FUNCTIONS ---
def get_exchange_rate_safe():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        if rate and rate > 0: return round(rate, 2)
        return None
    except: return None

def get_price_safe(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        price = stock.fast_info['last_price']
        if price and price > 0: return price
        hist = stock.history(period="1d")
        if not hist.empty: return hist['Close'].iloc[-1]
        return 0
    except: return 0

# --- 3. MAIN APP UI ---
st.set_page_config(page_title="AP Wealth OS", page_icon="💰")
st.title("💰 AP Wealth OS")

# 3.1 เลือกผู้ใช้งาน
user_name = st.selectbox("👤 ใครกำลังใช้งาน?", list(FAMILY_PORTFOLIOS.keys()))
user_data = FAMILY_PORTFOLIOS[user_name]
currency = user_data['currency']
is_usd_port = (currency == "USD")

# 3.2 ตั้งค่างบประมาณ
col1, col2 = st.columns(2)
with col1:
    budget_thb = st.number_input("💵 เงินลงทุนเดือนนี้ (บาท)", value=10000, step=1000)

with col2:
    if is_usd_port:
        auto_rate = get_exchange_rate_safe()
        default_rate = auto_rate if auto_rate else 34.50
        exchange_rate = st.number_input("💱 เรทเงิน (บาท/$)", value=default_rate, step=0.01)
        budget_calc = budget_thb / exchange_rate
        st.info(f"คิดเป็นเงิน: **${budget_calc:,.2f}**")
    else:
        exchange_rate = 1.0
        budget_calc = budget_thb
        st.info(f"คิดเป็นเงิน: **{budget_calc:,.0f} บาท**")

# --- 4. CALCULATION ENGINE ---
if st.button("🚀 คำนวณแผนการซื้อ (Calculate)", type="primary"):
    
    # 4.1 เตรียมข้อมูล
    tickers = list(user_data['assets'].keys())
    prices = {}
    progress_text = "⏳ กำลังเช็คราคาตลาด..."
    my_bar = st.progress(0, text=progress_text)
    manual_input_needed = []

    # 4.2 ดึงราคา
    for i, ticker in enumerate(tickers):
        my_bar.progress((i + 1) / len(tickers), text=f"เช็คราคา: {ticker}")
        price = get_price_safe(ticker)
        if price > 0: prices[ticker] = price
        else: manual_input_needed.append(ticker)
    my_bar.empty()

    # 4.3 กรณีดึงไม่ได้ (Manual Fallback)
    if manual_input_needed:
        st.error("⚠️ ดึงราคาไม่ได้บางตัว กรุณากรอกเอง:")
        with st.form("manual_price"):
            for t in manual_input_needed:
                prices[t] = st.number_input(f"ราคา {t}:", min_value=0.0)
            if not st.form_submit_button("ยืนยัน"): st.stop()

    # 4.4 คำนวณ (Core Logic)
    plan_data = []
    total_spent = 0
    line_summary = f"📢 *แผนลงทุน {user_name}*\n🗓 {datetime.now().strftime('%d/%m/%Y')}\n💰 งบ: {budget_thb:,.0f} บาท\n\n🛒 *รายการที่ต้องซื้อ:*"

    for ticker, target_pct in user_data['assets'].items():
        target_amount = budget_calc * target_pct
        price = prices.get(ticker, 0)
        
        if price > 0:
            if is_usd_port:
                shares = round(target_amount / price, 4)
            else:
                shares = int(target_amount / price)
            
            cost_curr = shares * price
            cost_thb = cost_curr * exchange_rate
            
            plan_data.append({
                "หุ้น": ticker,
                "ราคา": price,
                "จำนวน": shares,
                f"รวม ({currency})": cost_curr,
                "รวม (บาท)": cost_thb
            })
            
            if shares > 0:
                line_summary += f"\n- {ticker}: {shares} หุ้น (~{cost_thb:,.0f} บ.)"
            total_spent += cost_thb

    # 4.5 แสดงผล (ต้อง Indent ย่อหน้าให้อยู่ใต้ if st.button เหมือนเดิมนะครับ)
    st.divider()
    st.success("✅ คำนวณเสร็จเรียบร้อย!")
    
    # สร้าง DataFrame
    df = pd.DataFrame(plan_data)
    
    # [แก้ตรงนี้] ตั้งค่า 'หุ้น' เป็น Index เพื่อไม่ให้โดน format เป็นตัวเลข
    if not df.empty:
        st.dataframe(
            df.set_index("หุ้น").style.format("{:,.2f}"), 
            use_container_width=True
        )
    else:
        st.warning("ไม่มีรายการที่ต้องซื้อในเดือนนี้")

    remaining = budget_thb - total_spent  
    
    c1, c2 = st.columns(2)
    with c1: st.metric("ยอดซื้อรวม", f"{total_spent:,.2f} บาท")
    with c2: st.metric("เงินเหลือ", f"{remaining:,.2f} บาท")

    line_summary += f"\n\n💡 เงินเหลือ: {remaining:,.2f} บาท"
    st.code(line_summary, language="text")

# --- 5. SNOWBALL GRAPH (กราฟอยู่นอก if ได้ เพราะไม่ได้ใช้ตัวแปร remaining) ---
st.divider()
st.subheader("📈 พลังของดอกเบี้ยทบต้น (Snowball Effect)")
years = st.slider("มองภาพอนาคต (ปี)", 5, 30, 20)
exp_return = 0.10 if is_usd_port else 0.08 
future_val = [budget_thb * 12 * y * ((1 + exp_return)**y) for y in range(1, years+1)]

st.line_chart(pd.DataFrame(future_val, columns=["มูลค่าพอร์ต"]))

