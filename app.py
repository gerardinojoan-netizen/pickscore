import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd

from nba_api.stats.static import players as nba_players
from nba_api.stats.endpoints import playergamelog


# =========================
# Config / Style
# =========================
st.set_page_config(
    page_title="PickScore",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

def inject_style():
    st.markdown(
        """
        <style>
          .stApp {
            background:
              radial-gradient(1200px 600px at 15% 5%, rgba(120,70,255,.25), transparent 60%),
              radial-gradient(900px 500px at 85% 10%, rgba(50,200,255,.18), transparent 60%),
              linear-gradient(180deg, #0B0F17 0%, #070A10 100%);
            color: #E9EEF6;
          }

          #MainMenu {visibility: hidden;}
          footer {visibility: hidden;}
          header {visibility: hidden;}

          .muted {
            color: rgba(233,238,246,.75);
            font-size: 14px;
            margin-top: 4px;
          }

          .card {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 16px;
            padding: 16px 16px 14px 16px;
            margin: 10px 0 14px 0;
            box-shadow: 0 8px 24px rgba(0,0,0,.35);
          }

          .pill {
            display: inline-block;
            padding: 8px 10px;
            border-radius: 14px;
            background: rgba(255,255,255,0.07);
            border: 1px solid rgba(255,255,255,0.12);
            margin-top: 8px;
          }

          .big {
            font-size: 40px;
            font-weight: 800;
            letter-spacing: .3px;
            margin: 6px 0 8px 0;
          }

          .btnhint {
            color: rgba(233,238,246,.70);
            font-size: 12px;
          }

          .good {
            background: rgba(60,220,150,.18);
            border: 1px solid rgba(60,220,150,.25);
            border-radius: 14px;
            padding: 12px 12px;
            margin-top: 10px;
          }
          .bad {
            background: rgba(255,80,80,.14);
            border: 1px solid rgba(255,80,80,.22);
            border-radius: 14px;
            padding: 12px 12px;
            margin-top: 10px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

inject_style()

st.markdown("<div class='big'>PickScore</div>", unsafe_allow_html=True)
st.markdown("<div class='muted'>Sistema Personal • NBA Only</div>", unsafe_allow_html=True)
st.markdown("<div class='muted'>Herramienta de apoyo. No garantiza ganancias.</div>", unsafe_allow_html=True)


# =========================
# History (persistencia)
# =========================
HISTORY_FILE = "pick_history.json"

def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history: list) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"No pude guardar historial: {e}")

if "history" not in st.session_state:
    st.session_state.history = load_history()


# =========================
# Helpers NBA
# =========================
STAT_MAP = {
    "Points": ("PTS", "Puntos"),
    "Rebounds": ("REB", "Rebotes"),
    "Assists": ("AST", "Asistencias"),
    "PRA": (None, "PRA"),
}

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_active_players():
    plist = nba_players.get_players()
    active = [p for p in plist if p.get("is_active")]
    # lista de dicts: {"id":..., "full_name":...}
    return active

@st.cache_data(ttl=60 * 30, show_spinner=False)
def find_player_id_by_name(name: str):
    name = (name or "").strip()
    if not name:
        return None, None

    # fuzzy de nba_api (suele funcionar bien)
    matches = nba_players.find_players_by_full_name(name)
    if not matches:
        # fallback contains
        all_players = nba_players.get_players()
        nlow = name.lower()
        matches = [p for p in all_players if nlow in p["full_name"].lower()]

    if not matches:
        return None, None

    # prioriza activo si existe
    active = [p for p in matches if p.get("is_active")]
    pick = active[0] if active else matches[0]
    return int(pick["id"]), pick["full_name"]

@st.cache_data(ttl=60 * 15, show_spinner=False)
def fetch_last_games(player_id: int, season: str, n_games: int = 10) -> pd.DataFrame:
    try:
        gl = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season,
            season_type_all_star="Regular Season"
        )

        dfs = gl.get_data_frames()

        if not dfs or dfs[0] is None or dfs[0].empty:
            return pd.DataFrame()

        df = dfs[0].copy()

    except Exception:
        return pd.DataFrame()

    # ordenar por fecha
    if "GAME_DATE" in df.columns:
        try:
            df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"])
        except Exception:
            df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")

        df = df.sort_values("GAME_DATE_DT", ascending=False)

    return df.head(n_games).reset_index(drop=True)

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def compute_pickscore(
    df: pd.DataFrame,
    stat_label: str,
    direction: str,
    line_used: float,
    role: str,
    blowout: str,
):
    """
    Devuelve:
    - pick_score (0..100)
    - hit_rate (0..1)
    - volatility (std)
    - recommendation (PLAY/PASS)
    - confidence (0..100)
    """
    stat_key, _ = STAT_MAP[stat_label]

    # Construir serie
    if stat_label == "PRA":
        if all(c in df.columns for c in ["PTS", "REB", "AST"]):
            series = df["PTS"] + df["REB"] + df["AST"]
        else:
            series = None
    else:
        series = df[stat_key] if stat_key in df.columns else None

    if series is None:
       return 0.0, 0.0, 0.0, "PASS", 0

    series = series.astype(float)
    volatility = float(series.std(ddof=0)) if len(series) else 0.0

    if direction == "MORE":
        hits = (series > line_used).sum()
    else:
        hits = (series < line_used).sum()

    n = len(series)
    hit_rate = float(hits / n) if n else 0.0

    # Score base
    hits_score = 55 * hit_rate             # hasta 55 pts
    vol_penalty = clamp(volatility, 0, 12) * 2.2  # hasta -26 aprox

    # bonificaciones simples
    role_bonus = {"Estrella": 6, "Titular normal": 3, "Jugador de rol": 0}.get(role, 0)
    blow_penalty = {"Bajo": 0, "Medio": -3, "Alto": -8}.get(blowout, -3)

    # Dirección: MORE suele ser “más estable”
    dir_bonus = 2 if direction == "MORE" else 0

    score = 35 + hits_score + role_bonus + blow_penalty + dir_bonus - vol_penalty
    pick_score = float(clamp(score, 0, 100))

    # Recomendación PRO (simple y clara)
    # PLAY si score >= 60 y hit_rate >= 0.60 y volatilidad no muy alta
        # Confianza
    # base en score + castigo por volatilidad
    confidence = int(clamp(pick_score - (volatility * 3), 0, 100))

    # =========================
    # Recomendación PRO (3 niveles)
    # =========================
    if pick_score >= 70 and confidence >= 60 and volatility <= 3.0:
        recommendation = "STRONG"
        rec_mode = "JUGAR (Power)"
    elif pick_score >= 60 and confidence >= 50 and volatility <= 4.0:
        recommendation = "PLAYABLE"
        rec_mode = "FLEX (con cuidado)"
    else:
        recommendation = "PASS"
        rec_mode = "NO JUGAR"

    return pick_score, hit_rate, volatility, recommendation, confidence, rec_mode


# =========================
# Historial UI
# =========================
with st.expander("📒 Historial (guardar picks)", expanded=False):
    alias = st.text_input("Tu alias (por ahora)", value="Joan")

    if len(st.session_state.history) == 0:
        st.info("Todavía no hay picks guardados.")
    else:
        dfh = pd.DataFrame(st.session_state.history)
        st.dataframe(dfh, use_container_width=True, hide_index=True)

    cA, cB = st.columns(2)
    with cA:
        if st.button("🗑️ Borrar historial"):
            st.session_state.history = []
            save_history(st.session_state.history)
            st.success("Historial borrado.")
            st.rerun()
    with cB:
        st.caption("Tip: esto guarda en pick_history.json (persistencia básica).")


# =========================
# Inputs
# =========================
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.subheader("1) Selección rápida (tipo app)")

active_players = get_active_players()
player_names = sorted([p["full_name"] for p in active_players])

search_text = st.text_input("Buscar jugador (escribe parte del nombre)", value="")
filtered_names = player_names
if search_text.strip():
    s = search_text.strip().lower()
    filtered_names = [n for n in player_names if s in n.lower()]
    if len(filtered_names) == 0:
        filtered_names = player_names

player_name = st.selectbox("Jugador", filtered_names, index=0)

stat_label = st.selectbox("Stat", ["Points", "Rebounds", "Assists", "PRA"], index=0)

direction = st.radio("Dirección", ["MORE", "LESS"], horizontal=True, index=0)

st.markdown("</div>", unsafe_allow_html=True)


st.markdown("<div class='card'>", unsafe_allow_html=True)
st.subheader("2) Línea PRO automática + Ajustes")

season = st.text_input("Temporada", value="2025-26", help="Ej: 2025-26")
n_games = st.slider("Últimos N juegos", 5, 15, 10)

use_auto = st.checkbox("Usar línea PRO automática", value=True)
line_manual = st.number_input("Línea manual (si quieres)", min_value=0.0, value=0.0, step=0.5)

role = st.selectbox("Rol del jugador", ["Estrella", "Titular normal", "Jugador de rol"], index=1)
blowout = st.selectbox("Riesgo de blowout", ["Bajo", "Medio", "Alto"], index=1)

st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Result
# =========================
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.subheader("3) Resultado")

analyze = st.button("📊 Analizar", use_container_width=True)

if analyze:
    with st.spinner("Buscando jugador y trayendo últimos juegos..."):
        pid, full_name = find_player_id_by_name(player_name)

        if not pid:
            st.error("No encontré ese jugador. Prueba con nombre completo.")
            st.stop()

        df = fetch_last_games(pid, season=season, n_games=int(n_games))

        # calcular suggested_line
        stat_key, _ = STAT_MAP[stat_label]
        if stat_label == "PRA":
            if all(c in df.columns for c in ["PTS", "REB", "AST"]):
                df["_PRA"] = df["PTS"] + df["REB"] + df["AST"]
                suggested_line = float(df["_PRA"].tail(int(n_games)).mean())
            else:
                suggested_line = None
        else:
            if stat_key and stat_key in df.columns:
                suggested_line = float(df[stat_key].tail(int(n_games)).mean())
            else:
                suggested_line = None

        # línea final usada (evita NameError)
        line_used = float(suggested_line) if (use_auto and suggested_line is not None) else float(line_manual)

    # Mostrar qué línea se usó
    if use_auto and suggested_line is not None:
        st.markdown(
            f"<div class='good'>✅ Línea PRO automática (promedio últimos {int(n_games)}): <b>{suggested_line:.2f}</b></div>",
            unsafe_allow_html=True
        )
        st.caption(f"📌 Línea usada para el cálculo: {line_used:.2f} (AUTO)")
    else:
        st.markdown(
            f"<div class='pill'>📌 Línea usada para el cálculo: <b>{line_used:.2f}</b> (MANUAL)</div>",
            unsafe_allow_html=True
        )

    # Calcular score
    pick_score, hit_rate, volatility, recommendation, confidence = compute_pickscore(
        df=df,
        stat_label=stat_label,
        direction=direction,
        line_used=line_used,
        role=role,
        blowout=blowout,
    )

    st.markdown(f"<div class='big'>PickScore: {pick_score:.1f}/100</div>", unsafe_allow_html=True)

    # Recomendación PRO
    st.markdown("🧠 **Recomendación PRO**")
    if recommendation == "PLAY":
        st.markdown(
            f"<div class='good'>✅ <b>PLAY</b><br/>Modo sugerido: <b>JUGAR</b><br/>Confianza: <b>{confidence}%</b></div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"<div class='bad'>❌ <b>PASS</b><br/>Modo sugerido: <b>NO JUGAR</b><br/>Confianza: <b>{confidence}%</b></div>",
            unsafe_allow_html=True
        )

    st.markdown("📌 **Métricas**")
    st.write(f"• Hit rate últimos {int(n_games)}: **{hit_rate*100:.1f}%**")
    st.write(f"• Desviación (volatilidad): **{volatility:.2f}**")

    # Tabla últimos juegos
    st.markdown("📋 **Últimos juegos**")
    show_cols = ["GAME_DATE", "MATCHUP", "PTS", "REB", "AST"]
    existing = [c for c in show_cols if c in df.columns]
    st.dataframe(df[existing].head(int(n_games)), use_container_width=True, hide_index=True)

    # Guardar
    st.markdown("---")
    if st.button("💾 Guardar pick en historial", use_container_width=True):
        item = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "alias": (alias or "").strip(),
            "player": full_name or player_name,
            "player_id": int(pid),
            "stat": stat_label,
            "direction": direction,
            "season": season,
            "n_games": int(n_games),
            "line_used": round(float(line_used), 2),
            "line_auto": round(float(suggested_line), 2) if suggested_line is not None else None,
            "line_manual": round(float(line_manual), 2),
            "hit_rate": round(float(hit_rate), 4),
            "volatility": round(float(volatility), 4),
            "pick_score": round(float(pick_score), 1),
            "recommendation": recommendation,
            "confidence": int(confidence),
        }

        st.session_state.history.append(item)
        save_history(st.session_state.history)
        st.success("✅ Guardado en historial.")
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)
