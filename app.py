import streamlit as st
import pandas as pd
from datetime import datetime

from nba_api.stats.static import players as nba_players
from nba_api.stats.endpoints import playergamelog


# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="PickScore", layout="centered")
st.title("PickScore — Sistema Personal")
st.caption("Herramienta de apoyo. No garantiza ganancias.")


# ---------------------------
# Helpers
# ---------------------------
def clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


STAT_MAP = {
    "Points": ("PTS", "Puntos"),
    "Rebounds": ("REB", "Rebotes"),
    "Assists": ("AST", "Asistencias"),
    "PRA": (None, "PRA"),
}

TEAM_ABBR_TO_ID = {
    # NBA API usa IDs de team en otros endpoints,
    # aquí no lo necesitamos pero lo dejo por si después agregas “vs equipo”
}


@st.cache_data(ttl=60 * 30, show_spinner=False)
def find_player_id_by_name(name: str) -> tuple[int | None, str | None]:
    """
    Devuelve (player_id, full_name) usando búsqueda “fuzzy”.
    """
    name = (name or "").strip()
    if not name:
        return None, None

    # 1) fuzzy search de nba_api (suele funcionar bien)
    matches = nba_players.find_players_by_full_name(name)

    if not matches:
        # 2) intenta “contains” por si el usuario pone solo apellido
        all_players = nba_players.get_players()
        name_low = name.lower()
        matches = [p for p in all_players if name_low in p["full_name"].lower()]

    if not matches:
        return None, None

    # Prioriza active si existe
    active = [p for p in matches if p.get("is_active")]
    pick = active[0] if active else matches[0]

    return int(pick["id"]), pick["full_name"]


@st.cache_data(ttl=60 * 15, show_spinner=False)
def fetch_last_games(player_id: int, season: str, n_games: int = 10) -> pd.DataFrame:
    """
    Trae game logs y devuelve DataFrame con últimos N juegos.
    """
    gl = playergamelog.PlayerGameLog(player_id=player_id, season=season)
    df = gl.get_data_frames()[0]

    # Ordenar por fecha (GAME_DATE suele venir como string)
    # Ej: "FEB 25, 2026"
    if "GAME_DATE" in df.columns:
        try:
            df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"])
        except Exception:
            df["GAME_DATE_DT"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df = df.sort_values("GAME_DATE_DT", ascending=False)

    return df.head(n_games).reset_index(drop=True)


def current_season_guess() -> str:
    """
    Devuelve temporada NBA tipo '2025-26' según la fecha actual.
    """
    now = datetime.now()
    y = now.year
    # NBA season suele empezar en Oct
    if now.month >= 10:
        return f"{y}-{str(y+1)[-2:]}"
    else:
        return f"{y-1}-{str(y)[-2:]}"


def compute_stat_series(df: pd.DataFrame, stat_key: str) -> pd.Series:
    """
    Devuelve una serie con el stat elegido.
    """
    if stat_key == "PRA":
        return df["PTS"].astype(float) + df["REB"].astype(float) + df["AST"].astype(float)
    col = STAT_MAP[stat_key][0]
    return df[col].astype(float)


def over_count_last_n(values: pd.Series, line: float, direction: str, n: int = 5) -> int:
    last_n = values.head(n)
    if direction == "MORE":
        return int((last_n > line).sum())
    else:
        return int((last_n < line).sum())


def estimate_minutes_from_logs(df: pd.DataFrame) -> float:
    """
    MIN puede venir como '36' o '36:12'. Convertimos a minutos float.
    """
    if "MIN" not in df.columns:
        return 30.0

    def parse_min(x):
        if pd.isna(x):
            return None
        s = str(x)
        if ":" in s:
            mm, ss = s.split(":")
            try:
                return float(mm) + (float(ss) / 60.0)
            except Exception:
                return None
        try:
            return float(s)
        except Exception:
            return None

    mins = df["MIN"].apply(parse_min).dropna()
    if mins.empty:
        return 30.0
    return float(mins.head(10).mean())


def pickscore_model(avg10: float, over5: int, minutes: float, role: str, blowout: str, direction: str) -> float:
    """
    Modelo simple (pero útil):
    - base arranca 50
    - edge: qué tanto avg10 se separa de la línea (lo calculamos aparte)
    - hits: over5 (0-5) -> +0..+25
    - minutes: más minutos -> más chance (cap)
    - role bonus
    - blowout penalty
    """
    # Estos pesos los puedes tunear luego
    hits_score = (over5 / 5.0) * 25.0        # 0..25
    minutes_score = clamp((minutes - 24) * 1.0, 0, 18)  # 0..18 aprox

    role_bonus = 0
    if role == "Estrella":
        role_bonus = 10
    elif role == "Titular normal":
        role_bonus = 5
    else:
        role_bonus = 0

    blow_penalty = 0
    if blowout == "Medio":
        blow_penalty = -5
    elif blowout == "Alto":
        blow_penalty = -10

    # Dirección: MORE suele ser un poco más “estable” en ciertas stats
    dir_bonus = 2 if direction == "MORE" else 0

    score = 50 + hits_score + minutes_score + role_bonus + blow_penalty + dir_bonus
    return float(clamp(score, 0, 100))


# ---------------------------
# Inputs
# ---------------------------
st.subheader("1) Información del Pick")

c1, c2 = st.columns(2)

with c1:
    player_name = st.text_input("Jugador (Nombre)", placeholder="Ej: Jalen Brunson")
    stat = st.selectbox("Stat", ["Points", "Rebounds", "Assists", "PRA"])

with c2:
    line = st.number_input("Línea", min_value=0.0, value=0.0, step=0.5)
    direction = st.selectbox("Dirección", ["MORE", "LESS"])

st.subheader("2) Datos Automáticos + Ajustes")

season = st.text_input("Temporada (opcional)", value=current_season_guess(), help="Ej: 2025-26. Déjalo así si no sabes.")
n_games = st.slider("Juegos para promedio (últimos N)", 5, 15, 10)

role = st.selectbox("Rol del jugador", ["Estrella", "Titular normal", "Jugador de rol"])
blowout = st.selectbox("Riesgo de blowout", ["Bajo", "Medio", "Alto"])


# ---------------------------
# Fetch + Calculate
# ---------------------------
st.divider()
st.subheader("Resultado")

if not player_name or line <= 0:
    st.info("Escribe el nombre del jugador y una línea (> 0) para calcular.")
    st.stop()

with st.spinner("Buscando jugador y trayendo últimos juegos..."):
    pid, full_name = find_player_id_by_name(player_name)

if not pid:
    st.error("No encontré ese jugador. Prueba con nombre + apellido (ej: 'Jalen Brunson').")
    st.stop()

try:
    df = fetch_last_games(pid, season=season, n_games=max(n_games, 10))
except Exception as e:
    st.error("Falló la consulta a la NBA API. A veces pasa por rate limit. Intenta recargar en 30s.")
    st.stop()

if df.empty:
    st.error("No hay game logs para ese jugador/temporada.")
    st.stop()

values = compute_stat_series(df, stat_key=stat)

avg10 = float(values.head(n_games).mean())
over5 = int(over_count_last_n(values, line=line, direction=direction, n=5))
minutes_est = float(estimate_minutes_from_logs(df))

# Edge: qué tan lejos está el promedio de la línea (normalizado)
# Nota: lo usamos solo para mostrarte info y un micro ajuste visual
edge = avg10 - line
edge_norm = clamp((abs(edge) / max(1.0, line)) * 100.0, 0, 30)  # 0..30

score = pickscore_model(avg10=avg10, over5=over5, minutes=minutes_est, role=role, blowout=blowout, direction=direction)

# Probabilidad estimada simple basada en score (puedes tunear)
prob = clamp(50 + (score - 50) * 0.35, 0, 100)

# UI metrics
st.write(f"**Jugador detectado:** {full_name}")
st.metric("PickScore (0-100)", round(score, 1))
st.metric("Probabilidad estimada", f"{round(prob, 1)}%")

# Decision label
if score >= 70:
    st.success("✅ PICK BUENO")
elif score >= 60:
    st.warning("⚠️ SOLO FLEX")
else:
    st.error("❌ EVITAR")

# Debug / Breakdown
with st.expander("Ver desglose y últimos juegos"):
    st.write(f"**Stat:** {STAT_MAP[stat][1]} | **Línea:** {line} | **Dirección:** {direction}")
    st.write(f"**Promedio últimos {n_games}:** {round(avg10, 2)}")
    st.write(f"**Hits últimos 5:** {over5}/5")
    st.write(f"**Minutos estimados:** {round(minutes_est, 1)}")
    st.write(f"**Edge (avg - line):** {round(edge, 2)} (normalizado {round(edge_norm, 1)})")

    show = df.copy()
    show["STAT_SELECTED"] = values
    cols = [c for c in ["GAME_DATE", "MATCHUP", "MIN", "PTS", "REB", "AST", "STAT_SELECTED"] if c in show.columns]
    st.dataframe(show[cols].head(10), use_container_width=True)
