import streamlit as st
import pandas as pd
import numpy as np
import os, json, time
from datetime import datetime

import requests
from nba_api.stats.static import players as nba_players
from nba_api.stats.endpoints import playergamelog

# ----------------------------
# Config
# ----------------------------
APP_TITLE = "PickScore PRO"
HISTORY_FILE = "pick_history.json"

STAT_OPTIONS = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "3PT Made": "FG3M",
    "PRA (Pts+Reb+Ast)": "PRA",
}

# ----------------------------
# UI / Style
# ----------------------------
def inject_style():
    st.markdown(
        """
        <style>
          .stApp {
            background: radial-gradient(1200px 600px at 15% 5%, rgba(128,0,255,0.20), rgba(0,0,0,0.0)),
                        radial-gradient(900px 500px at 85% 10%, rgba(0,255,200,0.12), rgba(0,0,0,0.0)),
                        linear-gradient(180deg, #0B0F17 0%, #070A10 100%);
            color: #E9EEF6;
          }
          header, footer {visibility:hidden;}
          #MainMenu {visibility:hidden;}
          .block-container {padding-top: 1.2rem; padding-bottom: 4rem; max-width: 980px;}
          .card {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 18px;
            padding: 16px 16px 14px 16px;
            box-shadow: 0 14px 40px rgba(0,0,0,0.35);
          }
          .muted {opacity:0.80;}
          .pill {
            display:inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(255,255,255,0.06);
            font-size: 12px;
            margin-right: 6px;
          }
          .bigTitle {font-size: 44px; font-weight: 800; line-height: 1.05; margin:0;}
          .subTitle {font-size: 15px; opacity:0.85; margin-top: 6px;}
          .recBox {
            border-radius: 16px;
            padding: 14px;
            border: 1px solid rgba(255,255,255,0.12);
            background: rgba(255,255,255,0.06);
          }
          .good {border-color: rgba(0,255,150,0.35) !important;}
          .warn {border-color: rgba(255,170,0,0.35) !important;}
          .bad  {border-color: rgba(255,60,60,0.35) !important;}
          .kpi {font-size: 18px; font-weight: 700;}
          .small {font-size: 13px; opacity:0.85;}
          .sep {height: 10px;}
          button[kind="secondary"] p {font-size: 18px !important; font-weight: 800 !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="centered", initial_sidebar_state="collapsed")
inject_style()

# ----------------------------
# Persistence
# ----------------------------
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

if "history_db" not in st.session_state:
    st.session_state.history_db = load_history()

# ----------------------------
# NBA Helpers
# ----------------------------
@st.cache_data(ttl=60 * 60, show_spinner=False)
def get_all_players_active():
    plist = nba_players.get_players()
    active = [p for p in plist if p.get("is_active")]
    # Sort by last name-ish (full_name works OK)
    active = sorted(active, key=lambda x: x.get("full_name", ""))
    return active

def find_player_by_full_name(full_name: str):
    plist = get_all_players_active()
    for p in plist:
        if p.get("full_name") == full_name:
            return p
    return None

def headshot_url(player_id: int) -> str:
    # NBA CDN headshots
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"

def safe_image(url: str):
    try:
        r = requests.get(url, timeout=6)
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            st.image(url, use_container_width=True)
        else:
            st.caption("Foto no disponible.")
    except Exception:
        st.caption("Foto no disponible.")

@st.cache_data(ttl=60 * 10, show_spinner=False)
def fetch_last_games(player_id: int, season: str, n_games: int) -> pd.DataFrame:
    gl = playergamelog.PlayerGameLog(player_id=player_id, season=season)
    df = gl.get_data_frames()[0]

    # Ordenar por fecha
    if "GAME_DATE" in df.columns:
        # GAME_DATE suele venir tipo "FEB 25, 2026"
        df["_DT"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df = df.sort_values("_DT", ascending=False).drop(columns=["_DT"], errors="ignore")

    return df.head(int(n_games)).reset_index(drop=True)

def current_season_guess() -> str:
    now = datetime.now()
    # NBA season suele arrancar Oct; regla simple:
    if now.month >= 10:
        return f"{now.year}-{str(now.year+1)[-2:]}"
    else:
        return f"{now.year-1}-{str(now.year)[-2:]}"

def compute_stat_series(df: pd.DataFrame, stat_key: str) -> pd.Series:
    if stat_key == "PRA":
        if all(c in df.columns for c in ["PTS", "REB", "AST"]):
            return df["PTS"].fillna(0) + df["REB"].fillna(0) + df["AST"].fillna(0)
        return pd.Series(dtype=float)

    if stat_key in df.columns:
        return df[stat_key].fillna(0)

    return pd.Series(dtype=float)

def hit_rate_over_under(values: np.ndarray, line: float, direction: str) -> float:
    if len(values) == 0:
        return 0.0
    if direction == "MORE":
        hits = np.sum(values > line)
    else:
        hits = np.sum(values < line)
    return float(hits) / float(len(values))

def clamp(x, a, b):
    return max(a, min(b, x))

def decision_engine(pick_score: float, hit_rate: float, volatility: float):
    """
    Devuelve: (label, mode, css_class, confidence_pct, note)
    """
    # confidence en % (visual)
    confidence = clamp(pick_score, 0, 100)

    if pick_score >= 75 and hit_rate >= 0.60 and volatility <= 5:
        return ("🔥 PLAY STRONG", "POWER", "good", confidence, "Alta consistencia + buen hit rate.")
    if pick_score >= 60 and hit_rate >= 0.55:
        return ("✅ BUENA JUGADA", "POWER / FLEX", "good", confidence, "Sólida. Si quieres bajar riesgo: FLEX.")
    if pick_score >= 45:
        return ("⚠️ FLEX PLAY", "FLEX", "warn", confidence, "Riesgo medio. Mejor FLEX o bajar stake.")
    return ("❌ PASS", "NO JUGAR", "bad", confidence, "Bajo score o volatilidad alta.")

def pick_score_formula(hit_rate: float, volatility: float, role: str, blowout: str, direction: str):
    # Base
    score = 50.0

    # Hit rate impact
    score += (hit_rate - 0.50) * 80.0   # +40 si 1.00, -40 si 0.00

    # Volatility penalty
    score -= float(volatility) * 2.0

    # Role bonus
    role_bonus = {"Estrella": 6, "Titular normal": 3, "Jugador de rol": 0}.get(role, 0)
    score += role_bonus

    # Blowout penalty
    blow_penalty = {"Bajo": 0, "Medio": -4, "Alto": -8}.get(blowout, -4)
    score += blow_penalty

    # Direction small bonus (solo para estabilidad de MORE en ciertas stats)
    if direction == "MORE":
        score += 2.0

    return float(clamp(score, 0, 100))

# ----------------------------
# Header
# ----------------------------
st.markdown(f'<p class="bigTitle">{APP_TITLE}</p>', unsafe_allow_html=True)
st.markdown('<div class="subTitle">Sistema Personal • NBA Only • Herramienta de apoyo. No garantiza ganancias.</div>', unsafe_allow_html=True)
st.markdown('<div class="sep"></div>', unsafe_allow_html=True)

# ----------------------------
# History UI
# ----------------------------
with st.expander("📒 Historial (guardar picks)", expanded=True):
    alias = st.text_input("Tu alias (para guardar tus picks)", value=st.session_state.get("alias", "Joan"), key="alias_input")
    st.session_state.alias = alias

    history_for_alias = st.session_state.history_db.get(alias, [])

    if len(history_for_alias) == 0:
        st.caption("Todavía no hay picks guardados.")
    else:
        dfh = pd.DataFrame(history_for_alias)
        # formateo
        if "ts" in dfh.columns:
            dfh["ts"] = pd.to_datetime(dfh["ts"], errors="coerce")
            dfh = dfh.sort_values("ts", ascending=False)
            dfh["ts"] = dfh["ts"].dt.strftime("%Y-%m-%d %H:%M")

        show_cols = [c for c in ["ts","player","stat","direction","line_used","hit_rate","volatility","pick_score","recommendation","mode"] if c in dfh.columns]
        st.dataframe(dfh[show_cols], use_container_width=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("⬇️ Exportar CSV", use_container_width=True):
                st.download_button(
                    "Descargar",
                    dfh.to_csv(index=False).encode("utf-8"),
                    file_name=f"pickscore_history_{alias}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        with c2:
            if st.button("🗑️ Borrar historial (alias)", use_container_width=True):
                st.session_state.history_db[alias] = []
                save_history(st.session_state.history_db)
                st.success("Historial borrado.")
                st.rerun()
        with c3:
            st.caption("Tip: tu historial se guarda en un JSON del app.")

st.markdown('<div class="sep"></div>', unsafe_allow_html=True)

# ----------------------------
# 1) Quick selection (App-like)
# ----------------------------
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown("## 1) Selección rápida (tipo app)")

all_active = get_all_players_active()
all_names = [p["full_name"] for p in all_active]

search = st.text_input("Buscar jugador (escribe parte del nombre)", value=st.session_state.get("search", ""), key="search_box")
st.session_state.search = search

filtered = all_names
if search.strip():
    s = search.strip().lower()
    filtered = [n for n in all_names if s in n.lower()]
    if len(filtered) == 0:
        filtered = all_names

player_name = st.selectbox("Jugador", filtered, index=0, key="player_select")
player_obj = find_player_by_full_name(player_name)

stat_label = st.selectbox("Stat", list(STAT_OPTIONS.keys()), index=0, key="stat_select")

direction = st.radio("Dirección", ["MORE", "LESS"], horizontal=True, index=0, key="dir_radio")

st.markdown("</div>", unsafe_allow_html=True)
st.markdown('<div class="sep"></div>', unsafe_allow_html=True)

# Player photo card
if player_obj:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    cimg, cinfo = st.columns([1, 1])
    with cimg:
        safe_image(headshot_url(player_obj["id"]))
    with cinfo:
        st.markdown(f"### {player_obj['full_name']}")
        st.markdown(f"<span class='pill'>NBA</span><span class='pill'>ID: {player_obj['id']}</span>", unsafe_allow_html=True)
        st.caption("Foto vía NBA CDN. Si no aparece, es normal en algunos jugadores.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="sep"></div>', unsafe_allow_html=True)

# ----------------------------
# 2) Auto line + controls
# ----------------------------
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown("## 2) Línea PRO automática + ajustes")

season = st.text_input("Temporada", value=st.session_state.get("season", current_season_guess()), key="season_input")
st.session_state.season = season

n_games = st.slider("Últimos N juegos", 5, 20, int(st.session_state.get("n_games", 10)), key="n_games_slider")
st.session_state.n_games = n_games

use_auto = st.checkbox("Usar línea PRO automática", value=st.session_state.get("use_auto", True), key="use_auto_cb")
st.session_state.use_auto = use_auto

line_manual = st.number_input("Línea manual (si quieres)", min_value=0.0, value=float(st.session_state.get("line_manual", 0.0)), step=0.5, key="line_manual_input")
st.session_state.line_manual = line_manual

role = st.selectbox("Rol del jugador", ["Estrella", "Titular normal", "Jugador de rol"], index=0, key="role_select")
blowout = st.selectbox("Riesgo de blowout", ["Bajo", "Medio", "Alto"], index=0, key="blow_select")

st.markdown("</div>", unsafe_allow_html=True)
st.markdown('<div class="sep"></div>', unsafe_allow_html=True)

# ----------------------------
# 3) Analyze
# ----------------------------
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown("## 3) Resultado")

btn = st.button("📊 Analizar", use_container_width=True)

if btn:
    if not player_obj:
        st.error("Selecciona un jugador válido.")
        st.stop()

    player_id = int(player_obj["id"])
    stat_key = STAT_OPTIONS[stat_label]

    with st.spinner("Buscando datos NBA y calculando..."):
        try:
            df = fetch_last_games(player_id, season, n_games)
        except Exception as e:
            st.error("Fallo consultando NBA API. A veces pasa por rate limit. Espera 30s y recarga.")
            st.stop()

        series = compute_stat_series(df, stat_key)
        if series.empty:
            st.error("No pude calcular esa stat con los datos disponibles.")
            st.stop()

        values = series.to_numpy(dtype=float)
        volatility = float(np.std(values, ddof=0))

        suggested_line = float(np.mean(values)) if len(values) else None

        # Línea final usada
        if use_auto and suggested_line is not None:
            line_used = suggested_line
            st.success(f"✅ Línea PRO automática (promedio últimos {n_games}): {line_used:.2f}")
            st.caption(f"📌 Línea usada para el cálculo: {line_used:.2f} (AUTO)")
        else:
            line_used = float(line_manual)
            st.info(f"📌 Línea usada para el cálculo: {line_used:.2f} (MANUAL)")

        hr = hit_rate_over_under(values, line_used, direction)
        score = pick_score_formula(hr, volatility, role, blowout, direction)
        rec, mode, css_class, conf, note = decision_engine(score, hr, volatility)

        st.markdown(f"<div class='recBox {css_class}'>", unsafe_allow_html=True)
        st.markdown(f"### 🧠 Recomendación PRO")
        st.markdown(f"**{rec}**")
        st.markdown(f"Modo sugerido: **{mode}**")
        st.caption(note)
        st.markdown(f"**Confianza:** {conf:.0f}%")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("### 📌 Métricas")
        st.markdown(f"- **PickScore:** **{score:.1f}/100**")
        st.markdown(f"- **Hit rate últimos {n_games}:** **{(hr*100):.1f}%** ({int(round(hr*n_games))}/{n_games})")
        st.markdown(f"- **Desviación (volatilidad):** **{volatility:.2f}**")

        # Mini tabla
        df_show = df.copy()
        df_show["STAT"] = series
        cols = ["GAME_DATE", "MATCHUP", "STAT"]
        existing = [c for c in cols if c in df_show.columns]
        if existing:
            st.dataframe(df_show[existing].head(n_games), use_container_width=True)

        # Guardar
        st.markdown('<div class="sep"></div>', unsafe_allow_html=True)
        if st.button("💾 Guardar pick en Historial", use_container_width=True):
            alias = st.session_state.get("alias", "Joan")
            item = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "player": player_name,
                "player_id": player_id,
                "stat": stat_label,
                "direction": direction,
                "season": season,
                "n_games": int(n_games),
                "line_used": round(float(line_used), 2),
                "line_auto": round(float(suggested_line), 2) if suggested_line is not None else None,
                "line_manual": round(float(line_manual), 2),
                "use_auto": bool(use_auto),
                "hit_rate": round(float(hr), 3),
                "volatility": round(float(volatility), 3),
                "pick_score": round(float(score), 1),
                "recommendation": rec,
                "mode": mode,
                "role": role,
                "blowout": blowout,
            }
            st.session_state.history_db.setdefault(alias, []).append(item)
            save_history(st.session_state.history_db)
            st.success("Listo: guardado en tu historial.")
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# Footer note
st.markdown('<div class="sep"></div>', unsafe_allow_html=True)
st.caption("⚠️ Nota: Este sistema es de apoyo. Apuestas implican riesgo. Controla banca y juega responsable.")
