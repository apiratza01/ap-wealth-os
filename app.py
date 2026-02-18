import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import xml.etree.ElementTree as ET
import plotly.express as px
import math

# --- 0. AUTHENTICATION (ระบบล็อกอิน) ---
def check_password():
    """Returns `True` if the user had the correct password."""
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<h2 style='text-align: center;'>🔒 AP Wealth OS Login</h2>", unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([1,2,1])
    with col_b:
        password = st.text_input("กรุณาใส่รหัสผ่านครอบครัว", type="password")
        if st.button("เข้าสู่ระบบ", use_container_width=True):
            if password == "apmotor2026":  # <--- เปลี่ยนรหัสผ่านตรงนี้ตามต้องการ
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("รหัสผ่านไม่ถูกต้อง")
    return False

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
    try:
        url = f"https://finance.yahoo.com/rss/headline?s={ticker_symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        root = ET.fromstring(response.content)
        news_items = []
        for item in root.findall('./channel/item')[:5]:
            news_items.append({
                'title': item.find('title').text,
                'link': item.find('link').text,
                'published': item.find('pubDate').text if item.find('pubDate') is not None else ""
            })
        return news_items
    except: return []

def get_exchange_rate_safe():
    try:
        ticker = yf.Ticker("THB=X")
        rate = ticker.fast_info['last_price']
        return round(rate, 2) if rate and rate > 0 else None
    except: return None

def get_price_safe(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        price = stock.fast_info['last_price']
        if price and price > 0: return price
        hist = stock.history(period="1d")
        return hist['Close'].iloc[-1] if not hist.empty else 0
    except: return 0

def get_gsheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def save_to_gsheet(data_rows):
    try:
        client = get_gsheet_client()
        sheet = client.open("AP_Wealth_DB").sheet1
        for row in data_rows: sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"บันทึกไม่สำเร็จ: {e}")
        return False

def load_history(user_filter=None):
    try:
        client = get_gsheet_client()
        sheet = client.open("AP_Wealth_DB").sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if user_filter and not df.empty:
            df = df[df['User'] == user_filter]
        return df
    except: return pd.DataFrame()

# --- 3. MAIN LOGIC & UI ---
if check_password():
    st.set_page_config(page_title="AP Wealth OS", page_icon="💰", layout="wide")

    # Sidebar: Profile & News
    with st.sidebar:
        st.header("👤 Profile")
        user_name = st.selectbox("เลือกผู้ใช้งาน", list(FAMILY_PORTFOLIOS.keys()))
        user_data = FAMILY_PORTFOLIOS[user_name]
        currency = user_data['currency']
        is_usd_port = (currency == "USD")
        
        st.divider()
        st.subheader("📰 ข่าวหุ้นล่าสุด")
        all_tickers = list(user_data['assets'].keys())
        selected_news_ticker = st.selectbox("เลือกหุ้นเพื่ออ่านข่าว:", all_tickers, index=0)
        
        news_items = get_news_rss(selected_news_ticker)
        if news_items:
            for item in news_items:
                st.markdown(f"➤ **[{item['title']}]({item['link']})**")
                if item['published']:
                    short_date = item['published'].replace(" +0000", "").replace(" GMT", "")
                    st.caption(f"🕒 {short_date}")
                st.markdown("---")
            if st.button("🔄 รีเฟรชข่าว"): st.rerun()
        else: st.info("ไม่พบข่าวใหม่")

    tab_calc, tab_hist, tab_port = st.tabs(["🚀 แผนลงทุน", "📜 ประวัติย้อนหลัง", "📊 สรุปภาพรวม"])
# --- TAB 1: CALCULATOR (SMART REBALANCING) ---
    with tab_calc:
        col1, col2 = st.columns(2)
        with col1:
            budget_thb = st.number_input("💵 เงินลงทุนเดือนนี้ (บาท)", value=10000, step=1000)
        with col2:
            if is_usd_port:
                auto_rate = get_exchange_rate_safe()
                exchange_rate = st.number_input("💱 เรทเงิน (บาท/$)", value=auto_rate if auto_rate else 34.50, step=0.01)
                budget_in_currency = budget_thb / exchange_rate
                st.info(f"คิดเป็นเงิน: **${budget_in_currency:,.2f}**")
            else:
                exchange_rate, budget_in_currency = 1.0, budget_thb
                st.info(f"คิดเป็นเงิน: **{budget_in_currency:,.0f} บาท**")

        if st.button("🚀 คำนวณแผนการซื้อ (Smart Rebalancing)", type="primary", use_container_width=True):
            tickers = list(user_data['assets'].keys())
            prices = {}
            
            # 1. ดึงราคาตลาดล่าสุด
            my_bar = st.progress(0, text="⏳ กำลังเช็คราคาตลาด...")
            for i, ticker in enumerate(tickers):
                my_bar.progress((i + 1) / len(tickers), text=f"เช็คราคา: {ticker}")
                prices[ticker] = get_price_safe(ticker)
            my_bar.empty()

            # 2. โหลดของเดิมที่มีอยู่ (Current Portfolio)
            existing_shares = {t: 0.0 for t in tickers}
            hist_df = load_history(user_name)
            if not hist_df.empty:
                # รวมจำนวนหุ้นที่เคยซื้อมาทั้งหมด
                group = hist_df.groupby('Ticker')['Shares'].sum()
                for t, s in group.items():
                    if t in existing_shares:
                        existing_shares[t] = s

            # 3. คำนวณมูลค่าพอร์ตปัจจุบัน (Current Market Value)
            current_port_value = 0
            for t in tickers:
                current_port_value += existing_shares[t] * prices.get(t, 0)
            
            # 4. เป้าหมายความมั่งคั่งรวม (ของเดิม + เงินใหม่)
            total_wealth_target = current_port_value + budget_in_currency
            
            plan_data = []
            total_spent_currency = 0
            line_summary = f"📢 *แผนลงทุน {user_name} (Smart Rebalance)*\n🗓 {datetime.now().strftime('%d/%m/%Y')}\n💰 งบ: {budget_thb:,.0f} บาท\n"

            # 5. วนลูปเช็คทีละตัว (Core Logic: Underweight vs Overweight)
            for ticker, target_pct in user_data['assets'].items():
                price = prices.get(ticker, 0)
                
                if price > 0:
                    # มูลค่าที่ "ควรจะมี" ตามเป้าหมาย
                    target_value = total_wealth_target * target_pct
                    
                    # มูลค่าที่ "มีอยู่จริง"
                    current_value = existing_shares[ticker] * price
                    
                    # ส่วนต่างที่ต้องเติม (Deficit)
                    shortfall = target_value - current_value
                    
                    shares_to_buy = 0
                    status = "✅ พอดี"
                    
                    if shortfall > 0:
                        # Case: Underweight (ขาด) -> ต้องซื้อเพิ่ม
                        # แต่ห้ามซื้อเกินงบที่มี (budget_in_currency)
                        amount_to_buy = min(shortfall, budget_in_currency - total_spent_currency)
                        
                        # ถ้าเหลือเศษงบน้อยมากให้ข้าม
                        if amount_to_buy > (price * 0.1): 
                            if is_usd_port:
                                shares_to_buy = round(amount_to_buy / price, 4)
                            else:
                                shares_to_buy = int(amount_to_buy / price)
                            
                            status = "🟢 ซื้อเพิ่ม"
                    else:
                        # Case: Overweight (เกิน) -> ไม่ซื้อ
                        status = "🔴 พักก่อน (Overweight)"
                        shares_to_buy = 0

                    cost_curr = shares_to_buy * price
                    cost_thb = cost_curr * exchange_rate
                    
                    # บันทึกผล
                    if shares_to_buy > 0:
                        plan_data.append({
                            "หุ้น": ticker, 
                            "สถานะ": status,
                            "ราคา": price, 
                            "จำนวน": shares_to_buy, 
                            f"รวม ({currency})": cost_curr, 
                            "รวม (บาท)": cost_thb
                        })
                        line_summary += f"\n- {ticker}: {shares_to_buy} หุ้น ({status})"
                        total_spent_currency += cost_curr

            # สรุปยอดเงินบาท
            total_spent_thb = total_spent_currency * exchange_rate
            remaining_thb = budget_thb - total_spent_thb

            st.session_state['plan_result'] = {
                'df': pd.DataFrame(plan_data), 'plan_data': plan_data,
                'total_spent': total_spent_thb, 'remaining': remaining_thb,
                'line_summary': line_summary + f"\n\n💡 เงินเหลือ: {remaining_thb:,.2f} บาท",
                'user_name': user_name
            }

        if 'plan_result' in st.session_state:
            # ... (ส่วนแสดงผลเหมือนเดิม ใช้โค้ดเดิมได้เลย) ...
            # เพียงแต่แนะนำให้ copy ส่วนแสดงผลของเดิมมาแปะต่อท้ายตรงนี้
            res = st.session_state['plan_result']
            st.divider()
            st.success("✅ คำนวณแบบ Rebalancing เรียบร้อย!")
            
            # ... (แสดง Metric / Table / Save Button แบบเดิม) ...
            # ก๊อปส่วนแสดงผลจากโค้ดเก่ามาใส่ตรงนี้ได้เลยครับ
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 ยอดซื้อรวม", f"{res['total_spent']:,.0f} บาท")
            m2.metric("🐷 เงินทอน", f"{res['remaining']:,.2f} บาท", delta_color="off")
            m3.metric("🎯 รายการ", f"{len(res['df'])} ตัว")

            col_chart, col_table = st.columns([1, 1])
            with col_chart:
                if not res['df'].empty:
                    fig = px.pie(res['df'], values='รวม (บาท)', names='หุ้น', hole=0.4, title="สัดส่วนการกระจายเงิน")
                    st.plotly_chart(fig, use_container_width=True)
            with col_table:
                 if not res['df'].empty:
                    st.dataframe(res['df'].set_index("หุ้น").style.format("{:,.2f}"), use_container_width=True)
                 else:
                    st.warning("พอร์ตสมดุลแล้ว ไม่ต้องซื้อเพิ่ม หรือ งบไม่พอซื้อหุ้นที่ขาด")

            c_save, c_copy = st.columns([1, 2])
            with c_save:
                if st.button("💾 บันทึก (Save)", use_container_width=True):
                    # ... (โค้ดบันทึกเดิม) ...
                    save_rows = [[datetime.now().strftime("%Y-%m-%d %H:%M:%S"), res['user_name'], i['หุ้น'], i['จำนวน'], i['ราคา'], i['รวม (บาท)'], "V3-Rebalance"] for i in res['plan_data']]
                    if save_to_gsheet(save_rows):
                        st.success("บันทึกแล้ว!"); st.balloons()
            with c_copy: st.code(res['line_summary'], language="text")

    # --- TAB 2: HISTORY ---
    with tab_hist:
        if st.button("🔄 โหลดประวัติล่าสุด"):
            hist_df = load_history(user_name)
            if not hist_df.empty:
                st.metric("💸 เงินสะสมรวม", f"{hist_df['Total_THB'].sum():,.0f} บาท")
                st.dataframe(hist_df.sort_values("Date", ascending=False), use_container_width=True)
   # เพิ่ม "Portfolio" เข้าไปใน List ของ Tabs


    with tab_port:
        st.header(f"📊 วิเคราะห์พอร์ตของ {user_name}")
        
        # 1. โหลดข้อมูลจาก Sheet มาคำนวณต้นทุน
        df_all = load_history(user_name)
        
        if not df_all.empty:
            # คำนวณยอดรวมรายหุ้น (Group By Ticker)
            summary = df_all.groupby('Ticker').agg({
                'Shares': 'sum',
                'Total_THB': 'sum'
            }).reset_index()
            
            summary['Avg_Price_THB'] = summary['Total_THB'] / summary['Shares']
            
            # 2. ดึงราคาตลาดปัจจุบันมาเทียบ
            current_prices = []
            for t in summary['Ticker']:
                p = get_price_safe(t) # ใช้ฟังก์ชันเดิมที่มีอยู่
                current_prices.append(p)
            
            summary['Current_Price'] = current_prices
            
            # กรณีหุ้นนอก ต้องคำนวณกลับเป็นบาท (ใช้เรทปัจจุบัน)
            rate = get_exchange_rate_safe() or 35.0
            summary['Market_Value_THB'] = summary.apply(
                lambda x: (x['Shares'] * x['Current_Price'] * rate) if ".BK" not in x['Ticker'] 
                else (x['Shares'] * x['Current_Price']), axis=1
            )
            
            # 3. คำนวณ P/L
            summary['P/L_Amount'] = summary['Market_Value_THB'] - summary['Total_THB']
            summary['P/L_Percent'] = (summary['P/L_Amount'] / summary['Total_THB']) * 100
            
            # --- แสดงผล Metric รวม ---
            total_cost = summary['Total_THB'].sum()
            total_value = summary['Market_Value_THB'].sum()
            total_pl = total_value - total_cost
            
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("💰 มูลค่าพอร์ตปัจจุบัน", f"{total_value:,.0f} บ.")
            col_p2.metric("📈 กำไร/ขาดทุนรวม", f"{total_pl:,.0f} บ.", f"{ (total_pl/total_cost)*100 :.2f}%")
            col_p3.metric("💵 ต้นทุนทั้งหมด", f"{total_cost:,.0f} บ.")
    
            # แสดงตารางวิเคราะห์
            st.subheader("🔍 รายละเอียดรายสินทรัพย์")
            st.dataframe(summary.set_index('Ticker').style.format("{:,.2f}"), use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลสำหรับวิเคราะห์ กรุณาบันทึกการลงทุนก่อน")        




