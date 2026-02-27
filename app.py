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

over5 = st.slider("Veces que pasó la línea en últimos 5", 0, 5, 0)

minutes = st.number_input("Minutos esperados", value=30)

role = st.selectbox("Rol del jugador", ["Estrella", "Titular normal", "Jugador de rol"])
blowout = st.selectbox("Riesgo de blowout", ["Bajo", "Medio", "Alto"])

if line > 0:

    edge = (avg10 - line) if direction == "MORE" else (line - avg10)

    edge_score = clamp((edge / max(1, line)) * 50 + 50, 0, 100)
    hits_score = (over5 / 5) * 100
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
st.divider()

st.subheader("3) Predicción PickScore")

if player:
    base = line

    # Modelo simple inicial
    tendencia = base * 0.15
    confianza = clamp(50 + tendencia, 0, 100)

    st.metric("Confianza del Pick (%)", round(confianza, 2))

    if confianza >= 65:
        st.success("🔥 Pick fuerte")
    elif confianza >= 50:
        st.warning("⚠️ Pick medio")
    else:
        st.error("❌ Pick débil")
st.divider()

st.subheader("3) Análisis PickScore")

if player and line > 0:
        # --- Modelo (versión 2) basado en tus inputs manuales ---
    # Inputs que ya tienes arriba:
    # avg10, over5, minutes, role, blowout, direction, line

    # 1) Base por desempeño reciente (promedio vs línea)
    #    Si el promedio está por encima de la línea, suma.
    base = 50 + ((avg10 - line) * 2.5)

    # 2) Consistencia: cuántas veces pasó la línea en últimos 5 (0-5)
    base += (over5 * 5)

    # 3) Minutos esperados: más minutos = más chance
    #    Normalizamos alrededor de 30 min
    base += (minutes - 30) * 0.8

    # 4) Rol del jugador
    if role == "Estrella":
        base += 6
    elif role == "Titular":
        base += 3
    else:  # "Banca"
        base -= 2

    # 5) Riesgo de blowout
    if blowout == "Alto":
        base -= 6
    elif blowout == "Medio":
        base -= 3
    else:  # "Bajo"
        base += 1

    # 6) Dirección del pick
    #    MORE = queremos que suba la probabilidad si base está alto
    #    LESS = invertimos la lógica (si base es alto, menos favorable)
    if direction == "LESS":
        base = 100 - base

    # 7) Clamp final 0-100
    score = clamp(base, 0, 100)

    st.metric("Confianza del Pick (%)", round(score, 2))

    # Etiqueta final
    if score >= 65:
        st.success("✅ PICK BUENO")
    elif score >= 50:
        st.warning("⚠️ Pick medio")
    else:
        st.error("❌ EVITAR")
    
