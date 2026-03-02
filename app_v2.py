import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

from nba_api.stats.static import players as nba_players
from nba_api.stats.endpoints import playergamelog

# -----------------------------
# CONFIG + ESTILO
# -----------------------------
st.set_page_config(
    page_title="PickScore",
    page_icon="🏀",
    layout="centered",
    initial_sidebar_state="collapsed"
)

def inject_style():
    st.markdown("""
    <style>
      .stApp{
        background: radial-gradient(1200px 600px at 15% 5%, rgba(168,85,247,.18), transparent 45%),
                    radial-gradient(900px 500px at 85% 10%, rgba(34,197,94,.10), transparent 40%),
                    linear-gradient(180deg, #0B0F17 0%, #070A10 100%);
        color:#E9EEF6;
      }
      header, footer { visibility:hidden; }
      #MainMenu { visibility:hidden; }

      .card{
        background: rgba(255,255,255,.06);
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 18px;
        padding: 1rem;
        box-shadow: 0 10px 30px rgba(0,0,0,.22);
        backdrop-filter: blur(10px);
        margin-bottom: 14px;
      }
      .muted{opacity:.85;}
      .pill{
        display:inline-block; padding:6px 10px; border-radius:999px;
        border:1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.06);
        margin-right:8px;
        font-size:13px;
      }
      .bigtitle{font-size:44px; font-weight:900; margin-bottom:6px;}
      .subtitle{font-size:16px; opacity:.85; margin-bottom:2px;}
      .tiny{font-size:13px; opacity:.75;}

      /* Botones pro */
      button[kind="secondary"]{
        background: linear-gradient(135deg, rgba(255,255,255,.16), rgba(255,255,255,.06)) !important;
        border: 1px solid rgba(255,255,255,.35) !important;
        color: #FFFFFF !important;
        font-size: 20px !important;
        font-weight: 900 !important;
        letter-spacing: 1px;
        border-radius: 16px !important;
        height: 62px !important;
        box-shadow: 0 8px 22px rgba(0,0,0,.45);
        backdrop-filter: blur(14px);
        transition: all .2s ease-in-out;
      }
      button[kind="secondary"]:hover{
        transform: scale(1.03);
        border: 1px solid rgba(255,255,255,.70) !important;
      }
    </style>
    """, unsafe_allow_html=True)

inject_style()

st.markdown("<div class='bigtitle'>PickScore</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Sistema Personal • NBA Only</div>", unsafe_allow_html=True)
st.markdown("<div class='tiny'>Herramienta de apoyo. No garantiza ganancias.</div>", unsafe_allow_html=True)
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# -----------------------------
# HELPERS
# -----------------------------
STAT_OPTIONS = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "PRA (Pts+Reb+Ast)": "PRA",
}

def headshot_url(player_id: int) -> str:
    return f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"

@st.cache_data(ttl=60*60, show_spinner=False)
def get_active_players():
    plist = [p for p in nba_players.get_players() if p.get("is_active")]
    # diccionarios útiles
    name_to_id = {p["full_name"]: p["id"] for p in plist}
    id_to_name = {p["id"]: p["full_name"] for p in plist}
    return plist, name_to_id, id_to_name

@st.cache_data(ttl=60*10, show_spinner=False)
def fetch_last_games(player_id: int, season: str, n_games: int) -> pd.DataFrame:
    gl = playergamelog.PlayerGameLog(player_id=player_id, season=season)
    df = gl.get_data_frames()[0]
    # Orden por fecha (GAME_DATE viene string)
    if "GAME_DATE" in df.columns:
        df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df = df.sort_values("GAME_DATE_DT", ascending=False)
    return df.head(n_games).reset_index(drop=True)

def current_season_guess() -> str:
    # NBA season string tipo "2025-26"
    now = datetime.now()
    y = now.year
    # usualmente la temporada arranca en Oct
    if now.month >= 10:
        return f"{y}-{str(y+1)[-2:]}"
    return f"{y-1}-{str(y)[-2:]}"

# -----------------------------
# HISTORIAL (simple JSON por ahora)
# -----------------------------
HISTORY_FILE = "pick_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(items):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

if "history" not in st.session_state:
    st.session_state.history = load_history()

# -----------------------------
# UI: HISTORIAL
# -----------------------------
with st.expander("📒 Historial (guardar picks)", expanded=True):
    alias = st.text_input("Tu alias (por ahora)", value="Joan")
    hist = st.session_state.history
    if alias.strip():
        view = [h for h in hist if h.get("alias", "").lower().strip() == alias.lower().strip()]
    else:
        view = hist

    if view:
        st.dataframe(pd.DataFrame(view)[::-1], use_container_width=True)
    else:
        st.caption("Todavía no hay picks guardados.")

st.markdown("<div class='card'>", unsafe_allow_html=True)

# -----------------------------
# UI: INPUTS PRO
# -----------------------------
st.subheader("1) Selección rápida (tipo app)")

plist, name_to_id, _ = get_active_players()

search = st.text_input("Buscar jugador (escribe parte del nombre)", value="")
filtered_names = sorted([n for n in name_to_id.keys() if search.lower() in n.lower()]) if search else sorted(name_to_id.keys())

cA, cB = st.columns([1, 1])

with cA:
    player_name = st.selectbox("Jugador", filtered_names, index=0)
    player_id = name_to_id[player_name]
    st.image(headshot_url(player_id), caption=player_name, use_container_width=True)

with cB:
    stat_label = st.selectbox("Stat", list(STAT_OPTIONS.keys()), index=0)
    direction = st.radio("Dirección", ["MORE", "LESS"], horizontal=True)

st.divider()

st.subheader("2) Línea PRO automática + Ajustes")
c1, c2, c3 = st.columns([1, 1, 1])

with c1:
    season = st.text_input("Temporada", value=current_season_guess(), help="Ej: 2025-26")

with c2:
    n_games = st.slider("Últimos N juegos", min_value=3, max_value=15, value=10)

with c3:
    use_auto = st.checkbox("Usar línea PRO automática", value=True)

line_manual = st.number_input("Línea manual (si quieres)", min_value=0.0, value=0.0, step=0.5)

# -----------------------------
# FETCH + CÁLCULO
# -----------------------------
st.subheader("3) Resultado")

if st.button("📊 Analizar", use_container_width=True, type="secondary"):
    with st.spinner("Buscando jugador y trayendo últimos juegos..."):
        df = fetch_last_games(player_id, season, n_games)

    if df is None or df.empty:
        st.error("No pude traer datos. Prueba otra temporada o recarga.")
        st.stop()

    stat_key = STAT_OPTIONS[stat_label]

    # construir PRA si hace falta
    if stat_key == "PRA":
        needed = ["PTS", "REB", "AST"]
        if all(c in df.columns for c in needed):
            df["PRA"] = df["PTS"] + df["REB"] + df["AST"]
        else:
            st.error("No están todas las columnas para PRA en los datos.")
            st.stop()

    if stat_key not in df.columns:
        st.error(f"No encontré la columna {stat_key} en los datos.")
        st.stop()

    suggested_line = float(df[stat_key].mean())
    line = suggested_line if use_auto else float(line_manual)

    st.caption(f"✅ Línea PRO automática (promedio últimos {n_games}): **{suggested_line:.2f}**")
    st.caption(f"📌 Línea usada para el cálculo: **{line:.2f}** ({'AUTO' if use_auto else 'MANUAL'})")

    # Probabilidad simple (no “garantía”): % de juegos que cumplió vs línea
    if direction == "MORE":
        hits = (df[stat_key] > line).sum()
    else:
        hits = (df[stat_key] < line).sum()

    hit_rate = hits / len(df) if len(df) else 0

    # “PickScore” simple: mezcla hit_rate + estabilidad (desv)
    std = float(df[stat_key].std()) if len(df) > 1 else 0.0
    stability = max(0.0, 1.0 - (std / (line + 1e-6)))  # heurística
    pick_score = (0.7 * hit_rate + 0.3 * stability) * 100
    pick_score = max(0, min(100, pick_score))

    st.markdown(f"### PickScore: **{pick_score:.1f}/100**")
    st.markdown(f"- Hit rate últimos {n_games}: **{hit_rate*100:.1f}%** ({hits}/{len(df)})")
    st.markdown(f"- Desviación (volatilidad): **{std:.2f}**")

    # mini tabla
    show_cols = ["GAME_DATE", "MATCHUP", stat_key]
    existing = [c for c in show_cols if c in df.columns]
    st.dataframe(df[existing].head(n_games), use_container_width=True)

    # Guardar al historial
    if st.button("💾 Guardar pick en Historial", use_container_width=True):
        item = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "alias": alias.strip(),
            "player": player_name,
            "player_id": player_id,
            "stat": stat_label,
            "direction": direction,
            "season": season,
            "n_games": n_games,
            "line_used": round(line_manual, 2),
            "line_auto": round(suggested_line, 2),
            "hit_rate": round(hit_rate, 3),
            "pick_score": round(pick_score, 1),
        }
        st.session_state.history.append(item)
        save_history(st.session_state.history)
        st.success("Listo: guardado en tu historial ✅")

st.markdown("</div>", unsafe_allow_html=True)
