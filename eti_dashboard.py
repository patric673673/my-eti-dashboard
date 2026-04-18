import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="Edge Tracking Index (ETI)", layout="wide")
st.title("🛡️ 市場微觀與定價錯誤預警儀表板 (ETI)")
st.markdown("針對 SPX / 原油之量化 Edge 監控系統")

# --- 側邊欄參數設定 ---
st.sidebar.header("系統設定")
# 提供自由輸入的欄位，預設為大盤指數
target_asset = st.sidebar.text_input("🎯 追蹤標的代碼 (Yahoo Finance)", value="^GSPC").strip().upper()

# 自動偵測：如果輸入原油，預設帶入原油恐慌指數，否則一律帶入 VIX 大盤恐慌指數
default_vix = "^OVX" if target_asset == "CL=F" else "^VIX"
vix_ticker = st.sidebar.text_input("📉 對應波動率指數 (IV)", value=default_vix).strip().upper()

d4_score = st.sidebar.slider("D4 執行力分數 (本週)", 0, 25, 20)

# --- 側邊欄小百科 ---
st.sidebar.markdown("---")
with st.sidebar.expander("📖 指數與名詞百科", expanded=False):
    st.markdown("""
    - **IV (隱含波動率)**  
      市場未來的「恐慌預期」或「保費」。越高代表避險情緒越濃。
    - **RV (歷史實現波動率)**  
      過去 30 天實際的漲跌劇烈程度。代表資產真實的狀況。
    - **RV/IV 波動率比率**  
      `正常`：IV > RV (保費通常略高於真實風險)  
      `定價錯誤 (Edge)`：RV > IV 或急升。真實震盪大，但市場定價太便宜，適合出手。
    - **Z-Score**  
      衡量目前的錯位狀況「有多反常」。數值越高(例如>1.5)代表異常程度越嚴重，優勢越大。
    - **D4 執行力分數**  
      您的專屬「風險煞車皮」。用來評估近期的紀律與身心狀態。若狀態極差請拉低，這會直接扣除總分，強制保護您不上頭亂交易。
    - **ETI 總分**  
      整合上述指標、籌碼面與您自身執行力的綜合打分：  
      🟢 **>75 分**：勝率極高，大膽抱單或加倉。  
      🔴 **<60 分**：無明顯優勢，回歸隨機，建議收手。
    """)

# --- 數據抓取函數 ---
@st.cache_data(ttl=3600)
def get_market_data(ticker, days=90):
    df = yf.download(ticker, period=f"{days}d")
    return df

# --- 計算邏輯 ---
df_asset = get_market_data(target_asset)
df_vix = get_market_data(vix_ticker)

if df_asset.empty or df_vix.empty:
    st.error(f"無法抓取數據（標的: {target_asset} 或 {vix_ticker}），請稍後再試。")
    st.stop()

# 1. 計算 RV (30日年化)
returns = np.log(df_asset['Close'] / df_asset['Close'].shift(1))
current_rv = float(returns.tail(30).std().iloc[0] if isinstance(returns.tail(30).std(), pd.Series) else returns.tail(30).std()) * np.sqrt(252) * 100
current_iv = float(df_vix['Close'].iloc[-1].iloc[0] if isinstance(df_vix['Close'].iloc[-1], pd.Series) else df_vix['Close'].iloc[-1])
rv_iv_ratio = current_rv / current_iv if current_iv else 0

# 2. 計算 Z-Score (波動率倒掛程度)
ratio_history = [] # 這裡簡化，實務上建議存入資料庫
# 假設歷史平均 1.12, 標準差 0.1
z_score = (rv_iv_ratio - 1.12) / 0.1 

# --- 分數計算邏輯 (D1-D3) ---
d1 = min(18, 12 + max(0, (rv_iv_ratio - 1.12) * 40))
# 模擬 D2, D3 數據 (實務上需串接 CBOE/SpotGamma API)
d2 = 15 if st.sidebar.checkbox("P/C Ratio > 1.07?", value=True) else 5
d3 = 10 if st.sidebar.checkbox("IV 開始下降 (Vanna Squeeze)?", value=True) else 0

total_eti = (d1 + d2 + d3 + d4_score)

# --- 視覺化看板 ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("ETI 總分", f"{total_eti:.1f}", delta="Edge 強度")
# 修正了原始程式碼中的 :.2pt 錯誤，改為 :.2f
col2.metric("RV/IV 比率", f"{rv_iv_ratio:.2f}", delta=f"Z-Score: {z_score:.1f}")
col3.metric("當前 RV", f"{current_rv:.1f}%")
col4.metric("當前 IV", f"{current_iv:.1f}")

# --- 儀表板圓盤圖 ---
fig_gauge = go.Figure(go.Indicator(
    mode = "gauge+number",
    value = total_eti,
    title = {'text': "交易訊號強度"},
    gauge = {
        'axis': {'range': [0, 100]},
        'bar': {'color': "darkblue"},
        'steps' : [
            {'range': [0, 40], 'color': "red"},
            {'range': [40, 60], 'color': "orange"},
            {'range': [60, 80], 'color': "yellow"},
            {'range': [80, 100], 'color': "green"}],
        'threshold': {'line': {'color': "black", 'width': 4}, 'thickness': 0.75, 'value': 75}
    }
))
st.plotly_chart(fig_gauge, use_container_width=True)

# --- 趨勢圖表 ---
st.subheader("波動率趨勢分析")
fig_trend = go.Figure()

# 為了防止 pandas 多重 index 報錯，將資料轉換成 1D array
rv_series = returns.rolling(30).std() * np.sqrt(252) * 100
rv_values = rv_series.iloc[:, 0].values if isinstance(rv_series, pd.DataFrame) else rv_series.values
iv_values = df_vix['Close'].iloc[:, 0].values if isinstance(df_vix['Close'], pd.DataFrame) else df_vix['Close'].values

fig_trend.add_trace(go.Scatter(x=df_asset.index, y=rv_values, name="RV (30D)"))
fig_trend.add_trace(go.Scatter(x=df_vix.index, y=iv_values, name="IV (VIX)"))
st.plotly_chart(fig_trend, use_container_width=True)

# --- 結論與建議 ---
st.subheader("💡 專家系統建議")
if total_eti >= 75:
    st.success("【該抱】市場出現嚴重定價錯誤（RV > IV），且情緒極端，適合堅守倉位或利用 Vanna Squeeze 加倉。")
elif total_eti >= 60:
    st.warning("【謹慎】具備一定 Edge，但須注意 Gamma Flip 價位壓力。")
else:
    st.error("【該收】Edge 已消失，市場回歸隨機波動，或執行力 D4 扣分過重，建議離場。")
