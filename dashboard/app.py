from pathlib import Path

import duckdb
import plotly.express as px
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "nintendo_sales.duckdb"

st.set_page_config(page_title="Nintendo Sales", layout="wide")
st.title("Nintendo Sales Dashboard")


@st.cache_resource
def get_conn():
    return duckdb.connect(str(DB_PATH), read_only=True)


conn = get_conn()

tab1, tab2 = st.tabs(["Zeitreihe", "Top-Seller"])

# ---------------------------------------------------------------------------
# Tab 1 - Time series
# ---------------------------------------------------------------------------
with tab1:
    alle_spiele = conn.execute(
        "SELECT DISTINCT title FROM gold.dim_game ORDER BY title"
    ).df()["title"].tolist()

    # Default selection: the two games with the highest lifetime sales (independent of the metric radio below)
    top_spiele = conn.execute(
        """
        SELECT g.title
        FROM gold.fct_sales f
        JOIN gold.dim_game g ON f.game_id = g.game_id
        GROUP BY g.title
        ORDER BY MAX(f.ltd_global_sales) DESC
        LIMIT 2
        """
    ).df()["title"].tolist()

    auswahl = st.multiselect("Spiele auswählen", alle_spiele, default=top_spiele)
    metrik = st.radio(
        "Metrik",
        ["global_sales", "ltd_global_sales"],
        format_func=lambda x: "Quartalssales" if x == "global_sales" else "Lifetime Sales",
        horizontal=True,
    )

    if auswahl:
        placeholders = ", ".join("?" * len(auswahl))
        df = conn.execute(
            f"""
            SELECT f.snapshot_date, g.title, f.global_sales, f.ltd_global_sales
            FROM gold.fct_sales f
            JOIN gold.dim_game g ON f.game_id = g.game_id
            WHERE g.title IN ({placeholders})
            ORDER BY f.snapshot_date
            """,
            auswahl,
        ).df()

        fig = px.line(
            df,
            x="snapshot_date",
            y=metrik,
            color="title",
            markers=True,
            labels={"snapshot_date": "Datum", metrik: "Verkäufe (Stück)", "title": "Spiel"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Bitte mindestens ein Spiel auswählen.")

# ---------------------------------------------------------------------------
# Tab 2 - Top sellers
# ---------------------------------------------------------------------------
with tab2:
    alle_plattformen = conn.execute(
        "SELECT DISTINCT name FROM gold.dim_platform ORDER BY name"
    ).df()["name"].tolist()

    default_plattformen = [p for p in alle_plattformen if p in ("Nintendo Switch", "Nintendo Switch 2")]
    plattform_filter = st.multiselect("Plattform", alle_plattformen, default=default_plattformen)
    top_n = st.slider("Top N", min_value=5, max_value=50, value=20)

    if plattform_filter:
        placeholders = ", ".join("?" * len(plattform_filter))
        df = conn.execute(
            f"""
            SELECT g.title, p.name AS platform, MAX(f.ltd_global_sales) AS ltd_global_sales
            FROM gold.fct_sales f
            JOIN gold.dim_game g ON f.game_id = g.game_id
            JOIN gold.dim_platform p ON f.platform_id = p.platform_id
            WHERE p.name IN ({placeholders})
            GROUP BY g.title, p.name
            ORDER BY ltd_global_sales DESC
            LIMIT ?
            """,
            plattform_filter + [top_n],
        ).df()

        fig = px.bar(
            df.sort_values("ltd_global_sales"),
            x="ltd_global_sales",
            y="title",
            color="platform",
            orientation="h",
            labels={"ltd_global_sales": "Lifetime Sales (Stück)", "title": "Spiel", "platform": "Plattform"},
        )
        fig.update_layout(height=max(400, top_n * 22))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Bitte mindestens eine Plattform auswählen.")
