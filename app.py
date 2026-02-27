import streamlit as st
import math

st.set_page_config(page_title="PickScore", layout="centered")
st.title("PickScore — Sistema Personal")
st.caption("Herramienta de apoyo. No garantiza ganancias.")

def clamp(x, a, b):
    return max(a, min(b, x))

st.subheader("1) Información del Pick")

c1, c2 = st.columns(2)

with c1:
    player = st.text_input("Jugador")
    stat = st.selectbox("Stat", ["Points", "Assists", "Rebounds", "PRA"])

with c2:
    line = st.number_input("Línea", value=0.0, step=0.5)
    direction = st.selectbox("Dirección", ["MORE", "LESS"])

st.subheader("2) Datos Manuales")

avg10 = st.number_input("Promedio últimos 10 juegos", value=0.0, step=0.1)
hits5 = st.slider("Veces que pasó la línea en últimos 5", 0, 5, 0)
minutes = st.number_input("Minutos esperados", value=30)

role = st.selectbox("Rol del jugador", ["Estrella", "Titular normal", "Jugador de rol"])
blowout = st.selectbox("Riesgo de blowout", ["Bajo", "Medio", "Alto"])

if line > 0:

    edge = (avg10 - line) if direction == "MORE" else (line - avg10)

    edge_score = clamp((edge / max(1, line)) * 50 + 50, 0, 100)
    hits_score = (hits5 / 5) * 100
    minutes_score = clamp((minutes - 20) * 3, 0, 100)

    role_bonus = 15 if role == "Estrella" else 8 if role == "Titular normal" else 0
    blow_penalty = 0 if blowout == "Bajo" else 8 if blowout == "Medio" else 15

    score = clamp(
        0.4 * edge_score +
        0.3 * hits_score +
        0.2 * minutes_score +
        role_bonus -
        blow_penalty,
        0,
        100
    )

    probability = clamp(0.45 + (score * 0.003), 0.45, 0.80)

    st.divider()
    st.subheader("Resultado")

    st.metric("PickScore (0-100)", round(score, 1))
    st.metric("Probabilidad estimada", f"{round(probability*100,1)}%")

    if score >= 80:
        st.success("🔥 PICK PREMIUM")
    elif score >= 65:
        st.info("✅ PICK BUENO")
    elif score >= 55:
        st.warning("⚠️ SOLO FLEX")
    else:
        st.error("❌ EVITAR")
