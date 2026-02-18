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
        "assets": {"SCHD": 0.40, "MSFT": 0.30, "AVGO": 0.30}
    },
    "ฟิวส์": {
        "currency": "USD",
        "assets": {"VOO": 0.50, "QQQ": 0.30, "VNM": 0.20}
    },
    "คุณพ่อ 🛡️ (Safe Haven)": {
        "currency": "USD",
        "assets": {"VOO": 0.60, "BRK-B": 0.40}
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

def get_gsheet_client():
    """เชื่อมต่อ Google Sheets และส่งคืน client"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def save_to_gsheet(data_rows):
    """บันทึกข้อมูลลง Google Sheet"""
    try:
        client = get_gsheet_client()
        sheet = client.open("AP_Wealth_DB").sheet1
        for row in data_rows:
            sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"บันทึกไม่สำเร็จ: {e}")
        return False

def load_history(user_filter=None):
    """ดึงข้อมูลประวัติจาก Google Sheet"""
    try:
        client = get_gsheet_client()
        sheet = client.open("AP_Wealth_DB").sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if user_filter and not df.empty:
            df = df[df['User'] == user_filter]
        return df
    except Exception as e:
        st.error(f"โหลดประวัติไม่สำเร็จ: {e}")
        return pd.DataFrame()

# --- 3. MAIN APP UI ---
st.set_page_config(page_title="AP Wealth OS", page_icon="💰", layout="wide") # ใช้ Layout กว้าง

st.title("💰 AP Wealth OS")
st.caption("ระบบวางแผนความมั่งคั่งครอบครัว (Family Wealth System)")

# Sidebar: เลือกผู้ใช้ & ข่าว
with st.sidebar:
    st.header("👤 Profile")
    user_name = st.selectbox("เลือกผู้ใช้งาน", list(FAMILY_PORTFOLIOS.keys()))
    user_data = FAMILY_PORTFOLIOS[user_name]
    currency = user_data['currency']
    is_usd_port = (currency == "USD")
    
    st.divider()
    
    # News Feed (ฟีเจอร์ใหม่)
    st.subheader(f"📰 ข่าวหุ้น ({user_name})")
    try:
        # ดึงข่าวของหุ้นตัวแรกในพอร์ต
        first_ticker = list(user_data['assets'].keys())[0]
        news = yf.Ticker(first_ticker).news
        if news:
            for item in news[:3]: # โชว์ 3 ข่าวล่าสุด
                st.markdown(f"**[{item['title']}]({item['link']})**")
                st.caption(f"Related: {', '.join(item.get('relatedTickers', []))}")
                st.markdown("---")
        else:
            st.info("ไม่มีข่าวล่าสุด")
    except:
        st.caption("ไม่สามารถโหลดข่าวได้")

# สร้าง Tabs แบ่งหน้าทำงาน
tab_calc, tab_hist = st.tabs(["🚀 แผนลงทุน (Calculator)", "📜 ประวัติย้อนหลัง (History)"])

# ==========================================
# TAB 1: CALCULATOR (หน้าคำนวณ)
# ==========================================
with tab_calc:
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

    # ปุ่มคำนวณ
    if st.button("🚀 คำนวณแผนการซื้อ", type="primary", use_container_width=True):
        
        # เตรียมข้อมูล
        tickers = list(user_data['assets'].keys())
        prices = {}
        my_bar = st.progress(0, text="⏳ กำลังเช็คราคาตลาด...")
        
        # ดึงราคา
        for i, ticker in enumerate(tickers):
            my_bar.progress((i + 1) / len(tickers), text=f"เช็คราคา: {ticker}")
            price = get_price_safe(ticker)
            if price > 0: prices[ticker] = price
        my_bar.empty()

        # คำนวณ (Core Logic)
        plan_data = []
        total_spent = 0
        line_summary = f"📢 *แผนลงทุน {user_name}*\n🗓 {datetime.now().strftime('%d/%m/%Y')}\n💰 งบ: {budget_thb:,.0f} บาท\n\n🛒 *รายการที่ต้องซื้อ:*"

        for ticker, target_pct in user_data['assets'].items():
            target_amount = budget_calc * target_pct
            price = prices.get(ticker, 0)
            
            if price > 0:
                shares = round(target_amount / price, 4) if is_usd_port else int(target_amount / price)
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

        remaining = budget_thb - total_spent
        line_summary += f"\n\n💡 เงินเหลือ: {remaining:,.2f} บาท"

        # บันทึกลง Session State
        st.session_state['plan_result'] = {
            'df': pd.DataFrame(plan_data),
            'plan_data': plan_data,
            'total_spent': total_spent,
            'remaining': remaining,
            'line_summary': line_summary,
            'user_name': user_name
        }

    # แสดงผลจาก Session State
    if 'plan_result' in st.session_state:
        result = st.session_state['plan_result']
        df = result['df']

        st.divider()
        
        if not df.empty:
            # 1. Dashboard Metrics (ตัวเลขใหญ่ๆ ดูง่าย)
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 ยอดซื้อรวม", f"{result['total_spent']:,.0f} บาท")
            m2.metric("🐷 เงินทอน", f"{result['remaining']:,.2f} บาท", delta_color="off")
            m3.metric("🎯 จำนวนรายการ", f"{len(df)} รายการ")

            # 2. Table in Expander (ซ่อนตารางไว้ กดเพื่อดู)
            with st.expander("📄 ดูรายการซื้อแบบละเอียด (คลิกเพื่อขยาย)", expanded=True):
                st.dataframe(df.set_index("หุ้น").style.format("{:,.2f}"), use_container_width=True)

            # 3. Save Button
            c_save, c_copy = st.columns([1, 2])
            with c_save:
                if st.button("💾 ยืนยันบันทึก (Save)", type="secondary"):
                    save_data = []
                    txn_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    for item in result['plan_data']:
                        row = [
                            txn_date,
                            result['user_name'],
                            item['หุ้น'],
                            float(item['จำนวน']),
                            float(item['ราคา']),
                            float(item['รวม (บาท)']),
                            "Auto-Plan V2"
                        ]
                        save_data.append(row)
                    
                    with st.spinner("กำลังบันทึก..."):
                        if save_to_gsheet(save_data):
                            st.success("บันทึกเรียบร้อย!")
                            st.balloons()
            
            with c_copy:
                st.code(result['line_summary'], language="text")
            
        else:
            st.warning("ไม่มีรายการที่ต้องซื้อ")

    # Snowball Graph (อยู่ด้านล่างสุดของ Tab 1)
    st.divider()
    with st.expander("📈 พลังของดอกเบี้ยทบต้น (Snowball Effect)", expanded=False):
        years = st.slider("มองภาพอนาคต (ปี)", 5, 30, 20)
        exp_return = 0.10 if is_usd_port else 0.08 
        future_val = [budget_thb * 12 * y * ((1 + exp_return)**y) for y in range(1, years+1)]
        st.line_chart(pd.DataFrame(future_val, columns=["มูลค่าพอร์ต"]))

# ==========================================
# TAB 2: HISTORY (หน้าประวัติ)
# ==========================================
with tab_hist:
    st.header(f"📜 ประวัติการลงทุนของ {user_name}")
    
    col_h1, col_h2 = st.columns([1, 3])
    with col_h1:
        if st.button("🔄 โหลดข้อมูลล่าสุด"):
            st.session_state['load_hist'] = True
            
    if st.session_state.get('load_hist'):
        with st.spinner("กำลังดึงข้อมูลจาก Google Sheet..."):
            df_hist = load_history(user_filter=user_name)
            
            if not df_hist.empty:
                # สรุปยอดรวม
                total_invested = df_hist['Total_THB'].sum()
                st.metric("💸 เงินต้นสะสมทั้งหมด", f"{total_invested:,.0f} บาท")
                
                # แสดงตาราง (เรียงวันที่ล่าสุดขึ้นก่อน)
                df_hist = df_hist.sort_values(by='Date', ascending=False)
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("ยังไม่มีข้อมูลบันทึกในระบบ")
