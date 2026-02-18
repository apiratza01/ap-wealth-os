import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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

def save_to_gsheet(data_rows):
    """บันทึกข้อมูลลง Google Sheet"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # ดึงจาก st.secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        # เปิดไฟล์ Sheet (แก้ชื่อไฟล์ตรงนี้ถ้าเปลี่ยนชื่อ)
        sheet = client.open("AP_Wealth_DB").sheet1
        
        for row in data_rows:
            sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"บันทึกไม่สำเร็จ: {e}")
        return False

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
# ปุ่มคำนวณ (เมื่อกด จะเก็บผลลัพธ์ลง Session State)
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

    # 4.3 กรณีดึงไม่ได้
    if manual_input_needed:
        st.error("⚠️ ดึงราคาไม่ได้บางตัว (ระบบจะหยุดทำงานชั่วคราว)")
        # ในเคส manual input ต้องจัดการแยกต่างหากเพื่อความง่ายใน V1 นี้ขอข้ามไปก่อน
        # หรือให้ใส่ราคา 0 ไปก่อนแล้วไปแก้ใน sheet

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
            
            # เก็บข้อมูลลง list
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

    remaining = budget_thb - total_spent
    line_summary += f"\n\n💡 เงินเหลือ: {remaining:,.2f} บาท"

    # --- บันทึกลง Session State (ความจำชั่วคราว) ---
    st.session_state['plan_result'] = {
        'df': pd.DataFrame(plan_data),
        'plan_data': plan_data,
        'total_spent': total_spent,
        'remaining': remaining,
        'line_summary': line_summary,
        'user_name': user_name # จำชื่อคนคำนวณไว้ด้วย
    }

# --- 5. RESULT DISPLAY (แสดงผลจากความจำ) ---
# ส่วนนี้จะทำงานตลอดเวลา ถ้ามีข้อมูลในความจำ
if 'plan_result' in st.session_state:
    result = st.session_state['plan_result']
    df = result['df']

    st.divider()
    st.success("✅ คำนวณเสร็จเรียบร้อย!")
    
    if not df.empty:
        # แสดงตาราง
        st.dataframe(df.set_index("หุ้น").style.format("{:,.2f}"), use_container_width=True)
        
        # แสดงยอดเงิน
        c1, c2 = st.columns(2)
        with c1: st.metric("ยอดซื้อรวม", f"{result['total_spent']:,.2f} บาท")
        with c2: st.metric("เงินเหลือ", f"{result['remaining']:,.2f} บาท")

        # --- ปุ่มบันทึกข้อมูล (Save) ---
        st.markdown("### 💾 บันทึกการลงทุน")
        
        # ปุ่มนี้อยู่นอก Block คำนวณแล้ว ทำให้กดได้จริง
        if st.button("ยืนยันการบันทึกเข้า Google Sheet"):
            save_data = []
            txn_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for item in result['plan_data']:
                row = [
                    txn_date,
                    result['user_name'],
                    item['หุ้น'],
                    float(item['จำนวน']),
                    float(item['ราคา']),
                    float(item['รวม (บาท)']), # ต้องตรงกับ key ใน dict
                    "Auto-Plan by AP Wealth"
                ]
                save_data.append(row)
            
            with st.spinner("กำลังบันทึก..."):
                if save_to_gsheet(save_data):
                    st.success(f"บันทึก {len(save_data)} รายการเรียบร้อยแล้ว!")
                    st.balloons()
                    # ลบความจำออกเพื่อให้เริ่มใหม่ (Optional)
                    # del st.session_state['plan_result'] 

        # แสดง Line Copy Code
        st.code(result['line_summary'], language="text")
        
    else:
        st.warning("ไม่มีรายการที่ต้องซื้อ")

# --- 6. SNOWBALL GRAPH ---
st.divider()
st.subheader("📈 พลังของดอกเบี้ยทบต้น (Snowball Effect)")
years = st.slider("มองภาพอนาคต (ปี)", 5, 30, 20)
exp_return = 0.10 if is_usd_port else 0.08 
future_val = [budget_thb * 12 * y * ((1 + exp_return)**y) for y in range(1, years+1)]

st.line_chart(pd.DataFrame(future_val, columns=["มูลค่าพอร์ต"]))
