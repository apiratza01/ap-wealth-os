import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests # <--- เพิ่ม
import xml.etree.ElementTree as ET # <--- เพิ่ม
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
    "Test": {
        "currency": "USD",
        "assets": {"VOO": 0.60, "BRK-B": 0.40}
    }
}

# --- 2. HELPER FUNCTIONS ---
def get_news_rss(ticker_symbol):
    """ดึงข่าวจาก Yahoo RSS Feed (เสถียรกว่า yfinance.news)"""
    try:
        # URL RSS ของ Yahoo Finance
        url = f"https://finance.yahoo.com/rss/headline?s={ticker_symbol}"
        
        # ต้องใส่ User-Agent เพื่อไม่ให้โดนมองว่าเป็น Bot
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        root = ET.fromstring(response.content)
        
        news_items = []
        # วนลูปดึงหัวข้อข่าว (item)
        for item in root.findall('./channel/item')[:5]: # เอา 5 ข่าวล่าสุด
            title = item.find('title').text
            link = item.find('link').text
            # พยายามดึงวันที่ (ถ้ามี)
            pubDate = item.find('pubDate')
            pub_date_str = pubDate.text if pubDate is not None else ""
            
            news_items.append({
                'title': title,
                'link': link,
                'published': pub_date_str
            })
            
        return news_items
    except Exception as e:
        # print(f"Error fetching news: {e}") # สำหรับ Debug ใน Console
        return []
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
    
    # --- ส่วนแสดงข่าว (News Feed) ปรับปรุงใหม่ ---
    st.subheader(f"📰 ข่าวหุ้น")
    
    # 1. ดึงรายชื่อหุ้นทั้งหมดในพอร์ตของคนนั้น
    all_tickers = list(user_data['assets'].keys())
    
    # 2. สร้างกล่องเลือกหุ้น (Default คือตัวแรก)
    selected_news_ticker = st.selectbox(
        "เลือกหุ้นที่ต้องการอ่านข่าว:", 
        all_tickers,
        index=0 # เริ่มต้นที่ตัวแรก
    )
    
    # 3. ดึงข่าวของตัวที่เลือก (ใช้ฟังก์ชัน RSS ที่เราเพิ่งทำ)
    # หมายเหตุ: ต้องมีฟังก์ชัน get_news_rss() อยู่ในไฟล์แล้วนะครับ
    news_items = get_news_rss(selected_news_ticker)
    
    if news_items:
        st.caption(f"ข่าวล่าสุดของ: {selected_news_ticker}")
        for item in news_items:
            st.markdown(f"➤ **[{item['title']}]({item['link']})**")
            if item.get('published'):
                # ตัดวันที่ให้สั้นลงเพื่อความสวยงาม
                date_str = item['published']
                # พยายามตัดคำว่า +0000 หรือ GMT ออกถ้ามี
                short_date = date_str.replace(" +0000", "").replace(" GMT", "")
                st.caption(f"🕒 {short_date}")
            st.markdown("---")
            
        if st.button("🔄 รีเฟรชข่าว"):
            st.rerun()
    else:
        st.info(f"ไม่พบข่าวของ {selected_news_ticker} (หรือไม่มีข่าวใหม่)")
        st.caption("ลองเปลี่ยนตัวเลือก หรือกดรีเฟรช")
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
    # Snowball Graph (อยู่ด้านล่างสุดของ Tab 1)
    st.divider()
    with st.expander("📈 พลังของดอกเบี้ยทบต้น (Snowball Effect) - แบบสมจริง", expanded=False):
        
        # 1. ส่วนปรับแต่งตัวแปร (Simulation)
        c_sim1, c_sim2, c_sim3 = st.columns(3)
        with c_sim1:
            years = st.slider("ระยะเวลาลงทุน (ปี)", 5, 40, 20)
        with c_sim2:
            # ค่า Default: หุ้นนอก 8%, หุ้นไทย 6% (ปรับลดลงมาให้ Conservative)
            default_return = 8.0 if is_usd_port else 6.0
            exp_return = st.number_input("ผลตอบแทนคาดหวัง (% ต่อปี)", value=default_return, step=0.5) / 100
        with c_sim3:
            inflation = st.number_input("เงินเฟ้อ (% ต่อปี)", value=3.0, step=0.5, help="เฉลี่ย 3% เพื่อดูมูลค่าเงินจริง") / 100

        # 2. คำนวณ (DCA Logic รายเดือน)
        months = years * 12
        monthly_invest = budget_thb # ใช้ค่าบาทในการคำนวณเพื่อให้เห็นภาพ
        
        data_wealth = []
        data_invested = []
        
        current_wealth = 0
        total_invested = 0
        
        # สูตร Real Return (ผลตอบแทนที่แท้จริงหลังหักเงินเฟ้อ)
        real_return_rate = ((1 + exp_return) / (1 + inflation)) - 1
        monthly_rate = real_return_rate / 12

        for m in range(1, months + 1):
            total_invested += monthly_invest
            # สูตรทบต้นรายเดือน: (เงินเก่า + เงินใหม่) * ดอกเบี้ยเดือนนี้
            current_wealth = (current_wealth + monthly_invest) * (1 + monthly_rate)
            
            # เก็บข้อมูลทุกๆ สิ้นปี เพื่อมาพล็อต (จะได้ไม่ถี่เกินไป)
            if m % 12 == 0:
                data_wealth.append(current_wealth)
                data_invested.append(total_invested)

        # 3. แสดงผลกราฟเปรียบเทียบ
        df_chart = pd.DataFrame({
            "เงินต้นที่ใส่ไป (Principal)": data_invested,
            "มูลค่าพอร์ตจริง (Wealth)": data_wealth
        }, index=range(1, years + 1))

        st.line_chart(df_chart, color=["#FF4B4B", "#00CC96"]) # สีแดง=เงินต้น, สีเขียว=กำไร

        # 4. สรุปตัวเลขปลายทาง
        final_wealth = data_wealth[-1]
        final_principal = data_invested[-1]
        profit = final_wealth - final_principal
        
        # จัด Format ให้ดูง่าย
        st.markdown(f"### 🏁 บทสรุปในอีก {years} ปีข้างหน้า")
        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("เงินต้นสะสม (จ่ายจริง)", f"{final_principal:,.0f} บ.")
        c_res2.metric("มูลค่าพอร์ต (หลังหักเงินเฟ้อ)", f"{final_wealth:,.0f} บ.", delta=f"+กำไร {profit:,.0f}")
        c_res3.metric("โตขึ้น", f"{final_wealth/final_principal:.1f} เท่า")

        st.caption(f"💡 หมายเหตุ: คำนวณโดยหักเงินเฟ้อ {inflation*100}% แล้ว เพื่อแสดง 'มูลค่าเงินที่แท้จริง' (Purchasing Power) ณ ปัจจุบัน")

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






