from __future__ import annotations

import calendar
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import requests
import streamlit as st
from scipy import stats

# 1. Peoject constants the same as with the notebook file

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Each location maps to latitude and longitude). The order matters, it is the fixed
# order used to assign categorical colours, so a county keeps its colour in
# every chart even when a filter removes its neighbours.
LOCATIONS: dict[str, tuple[float, float]] = {
    "Nairobi": (-1.2921, 36.8219),
    "Kisumu": (-0.0917, 34.7680),
    "Mombasa": (-4.0435, 39.6682),
    "Eldoret": (0.5143, 35.2698),
    "Nakuru": (-0.3031, 36.0800),
    "Garissa": (-0.4536, 39.6401),
}

START_DATE, END_DATE = "2015-01-01", "2024-12-31"

DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "windspeed_10m_max",
]

# Physically plausible (low, high) bounds for Kenya, used to flag outliers.
PLAUSIBLE_RANGES = {
    "temperature_2m_max": (5, 45),
    "temperature_2m_min": (-5, 35),
    "temperature_2m_mean": (0, 40),
    "precipitation_sum": (0, 300),
    "rain_sum": (0, 300),
    "windspeed_10m_max": (0, 120),
}

PRETTY = {
    "temperature_2m_max": "Max temperature (°C)",
    "temperature_2m_min": "Min temperature (°C)",
    "temperature_2m_mean": "Mean temperature (°C)",
    "precipitation_sum": "Precipitation (mm)",
    "rain_sum": "Rain (mm)",
    "windspeed_10m_max": "Max wind speed (km/h)",
}

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/cleaned")
CLEAN_CSV = CLEAN_DIR / "kenya_weather_cleaned.csv"

MAX_GAP_DAYS = 3          # gaps up to this length are linearly interpolated
DRY_DAY_DEFAULT = 1.0     # mm — a "dry day" threshold, WMO-style


# 2. visual system

SURFACE = "#fcfcfb"        # chart surface
PLANE = "#f9f9f7"          # page plane
INK = "#0b0b0b"            # primary ink
INK_2 = "#52514e"          # secondary ink
MUTED = "#898781"          # axis / label ink
GRID = "#e1e0d9"           # hairline gridline
AXIS = "#c3c2b7"           # baseline / axis

# Categorical slots, assigned in the fixed locations order
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
COUNTY_COLOR = {loc: SERIES[i] for i, loc in enumerate(LOCATIONS)}

# Sequential ramp — one hue, light to dark, for magnitude (heatmaps, bubbles).
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Diverging ramp — two hues plus a neutral grey midpoint, for polarity
# (above vs below normal). Red = deficit, blue = surplus.
DIV_RAIN = [
    [0.00, "#a52f2e"], [0.20, "#e34948"], [0.40, "#f3b0af"],
    [0.50, "#f0efec"],
    [0.60, "#9ec5f4"], [0.80, "#3987e5"], [1.00, "#184f95"],
]

# Status palette — reserved for state, never reused as a series colour.
STATUS = {
    "Low": "#0ca30c",
    "Moderate": "#fab219",
    "High": "#ec835a",
    "Severe": "#d03b3b",
}

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

pio.templates["kmd"] = go.layout.Template(
    layout=dict(
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif',
                  size=13, color=INK_2),
        title=dict(font=dict(size=16, color=INK), x=0, xanchor="left", pad=dict(b=14)),
        colorway=SERIES,
        margin=dict(l=70, r=30, t=56, b=56),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=AXIS,
                        font=dict(color=INK, size=12)),
        xaxis=dict(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=INK_2)),
                   showline=True, ticks="outside", tickcolor=AXIS, ticklen=4),
        yaxis=dict(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=INK_2))),
        # Legends sit below the plot: a top-anchored legend collides with the
        # left-aligned title, and the title has to win that fight.
        legend=dict(orientation="h", yanchor="top", y=-0.20, xanchor="left", x=0,
                    title=dict(text=""), font=dict(color=INK_2)),
    )
)
pio.templates.default = "kmd"


# 3. The data layer

def _fetch_location(lat: float, lon: float, max_retries: int = 6) -> dict:
    """Call the Open-Meteo archive API for one location, backing off on HTTP 429."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "Africa/Nairobi",
    }
    for attempt in range(max_retries):
        response = requests.get(BASE_URL, params=params, timeout=60)
        if response.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Open-Meteo rate limit exceeded after several retries.")


def _load_long_frame() -> pd.DataFrame:
    """Return the raw long-format frame, fetching and caching JSON if needed."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for loc, (lat, lon) in LOCATIONS.items():
        path = RAW_DIR / f"{loc.lower()}.json"
        if not path.exists():
            with st.spinner(f"Fetching {loc} from the Open-Meteo archive…"):
                json.dump(_fetch_location(lat, lon), open(path, "w"), indent=2)
        daily = json.load(open(path))["daily"]
        frame = pd.DataFrame({"date": daily["time"]})
        for var in DAILY_VARIABLES:
            frame[var] = daily.get(var)
        frame["location"] = loc
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


@st.cache_data(show_spinner="Preparing the ten-year daily record…")
def load_data() -> tuple[pd.DataFrame, dict]:
    """Load, assess and clean the dataset. Returns (cleaned frame, quality report)."""
    raw = _load_long_frame()
    expected = pd.date_range(START_DATE, END_DATE, freq="D")

    # --- Data quality assessment (reported in the Data & Method tab) --------
    report = {
        "rows_raw": len(raw),
        "locations": raw["location"].nunique(),
        "expected_days": len(expected),
        "nans": {v: int(raw[v].isna().sum()) for v in DAILY_VARIABLES},
        "duplicates": int(raw.duplicated(subset=["location", "date"]).sum()),
        "missing_dates": {
            loc: len(set(expected) - set(raw.loc[raw.location == loc, "date"]))
            for loc in LOCATIONS
        },
        "completeness": {
            loc: 100 * (raw.location == loc).sum() / len(expected) for loc in LOCATIONS
        },
        "outliers": {},
    }
    for var, (low, high) in PLAUSIBLE_RANGES.items():
        report["outliers"][var] = int((~raw[var].between(low, high) & raw[var].notna()).sum())

    # Cleaning the notebook's five steps
    clean = raw.drop_duplicates(subset=["location", "date"], keep="first").reset_index(drop=True)
    for var, (low, high) in PLAUSIBLE_RANGES.items():
        clean.loc[~clean[var].between(low, high) & clean[var].notna(), var] = np.nan
    clean = (
        pd.concat([
            clean[clean.location == loc].set_index("date").reindex(expected).assign(location=loc)
            for loc in LOCATIONS
        ])
        .rename_axis("date")
        .reset_index()
    )
    for loc in LOCATIONS:
        mask = clean.location == loc
        for var in DAILY_VARIABLES:
            clean.loc[mask, var] = clean.loc[mask, var].interpolate(
                method="linear", limit=MAX_GAP_DAYS, limit_direction="both"
            )
    report["remaining_nans"] = int(clean[DAILY_VARIABLES].isna().sum().sum())
    report["rows_clean"] = len(clean)

    clean = clean[["date", "location"] + DAILY_VARIABLES]
    clean["year"] = clean.date.dt.year
    clean["month"] = clean.date.dt.month
    clean["month_name"] = clean.month.map(lambda m: calendar.month_abbr[m])
    clean["doy"] = clean.date.dt.dayofyear

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    if not CLEAN_CSV.exists():
        clean.drop(columns=["month_name", "doy"]).to_csv(CLEAN_CSV, index=False)
    return clean, report


# 4. analytics

@st.cache_data(show_spinner=False)
def annual_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """Q1/Q3 — annual mean of daily mean temperature, per county per year."""
    return (df.groupby(["location", "year"], as_index=False)
              .agg(mean_temp=("temperature_2m_mean", "mean"),
                   mean_max=("temperature_2m_max", "mean"),
                   mean_min=("temperature_2m_min", "mean")))


@st.cache_data(show_spinner=False)
def annual_rainfall(df: pd.DataFrame) -> pd.DataFrame:
    """Q2 — total precipitation per county per year, plus its local anomaly."""
    out = df.groupby(["location", "year"], as_index=False).agg(rain=("precipitation_sum", "sum"))
    grp = out.groupby("location")["rain"]
    out["local_mean"] = grp.transform("mean")
    out["anomaly_pct"] = 100 * (out.rain - out.local_mean) / out.local_mean
    out["z"] = grp.transform(lambda s: (s - s.mean()) / s.std(ddof=1))
    return out


@st.cache_data(show_spinner=False)
def rainfall_variability(df: pd.DataFrame) -> pd.DataFrame:
    """Q2 — mean, standard deviation and coefficient of variation of annual rainfall."""
    yearly = annual_rainfall(df)
    out = (yearly.groupby("location")["rain"]
                 .agg(mean_mm="mean", sd_mm=lambda s: s.std(ddof=1),
                      min_mm="min", max_mm="max")
                 .reset_index())
    out["cv_pct"] = 100 * out.sd_mm / out.mean_mm
    return out.sort_values("cv_pct", ascending=False)


@st.cache_data(show_spinner=False)
def temperature_trends(df: pd.DataFrame) -> pd.DataFrame:
    """Q3 — OLS trend of annual mean temperature on year, with a 95% interval."""
    yearly = annual_temperature(df)
    rows = []
    for loc, grp in yearly.groupby("location"):
        if len(grp) < 3:
            continue
        fit = stats.linregress(grp.year, grp.mean_temp)
        n = len(grp)
        tcrit = stats.t.ppf(0.975, n - 2)
        rows.append({
            "location": loc,
            "slope_per_year": fit.slope,
            "per_decade": fit.slope * 10,
            "ci_low": (fit.slope - tcrit * fit.stderr) * 10,
            "ci_high": (fit.slope + tcrit * fit.stderr) * 10,
            "r_squared": fit.rvalue ** 2,
            "p_value": fit.pvalue,
            "n_years": n,
            "significant": bool(fit.pvalue < 0.05),
        })
    return pd.DataFrame(rows).sort_values("per_decade", ascending=False)


@st.cache_data(show_spinner=False)
def monthly_climatology(df: pd.DataFrame) -> pd.DataFrame:
    """Q4 — average rainfall received in each calendar month (mm/month)."""
    n_years = df.year.nunique()
    out = (df.groupby(["location", "month"], as_index=False)
             .agg(total=("precipitation_sum", "sum"),
                  mean_temp=("temperature_2m_mean", "mean")))
    out["mm_per_month"] = out.total / n_years
    out["month_name"] = out.month.map(lambda m: calendar.month_abbr[m])
    out["share_pct"] = 100 * out.total / out.groupby("location")["total"].transform("sum")
    return out


@st.cache_data(show_spinner=False)
def dry_spells(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Q5 — every run of consecutive days below the dry-day threshold."""
    rows = []
    for loc, grp in df.sort_values("date").groupby("location"):
        dry = grp.precipitation_sum < threshold
        blocks = (dry != dry.shift()).cumsum()
        for _, run in grp[dry].groupby(blocks[dry]):
            rows.append({"location": loc, "start": run.date.min(),
                         "end": run.date.max(), "days": len(run)})
    spells = pd.DataFrame(rows)
    if spells.empty:
        return spells
    spells["end_excl"] = spells.end + pd.Timedelta(days=1)
    spells["year"] = spells.start.dt.year
    return spells.sort_values("days", ascending=False)


@st.cache_data(show_spinner=False)
def vulnerability(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """
    Q5 — a composite drought-vulnerability index from four evidence strands:
      aridity      low average annual rainfall
      variability  high coefficient of variation of annual rainfall
      persistence  long consecutive dry spells
      heat stress  high average temperature (drives evaporative demand)
    Each strand is min-max scaled across the counties on screen, then averaged,
    so the index is explicitly RELATIVE to the counties being compared.
    """
    var = rainfall_variability(df).set_index("location")
    temp = annual_temperature(df).groupby("location").mean_temp.mean()
    spells = dry_spells(df, threshold)
    longest = (spells.groupby("location").days.max() if not spells.empty
               else pd.Series(0, index=var.index))
    dry_share = df.assign(d=df.precipitation_sum < threshold).groupby("location").d.mean() * 100

    out = pd.DataFrame({
        "location": var.index,
        "mean_mm": var.mean_mm,
        "cv_pct": var.cv_pct,
        "longest_dry_days": longest.reindex(var.index).fillna(0),
        "dry_day_pct": dry_share.reindex(var.index),
        "mean_temp": temp.reindex(var.index),
    }).reset_index(drop=True)

    def scale(s: pd.Series, invert: bool = False) -> pd.Series:
        rng = s.max() - s.min()
        norm = pd.Series(0.5, index=s.index) if rng == 0 else (s - s.min()) / rng
        return 1 - norm if invert else norm

    out["s_aridity"] = scale(out.mean_mm, invert=True)
    out["s_variability"] = scale(out.cv_pct)
    out["s_persistence"] = scale(out.longest_dry_days)
    out["s_heat"] = scale(out.mean_temp)
    strands = ["s_aridity", "s_variability", "s_persistence", "s_heat"]
    out["index"] = 100 * out[strands].mean(axis=1)
    out["tier"] = pd.cut(out["index"], [-0.1, 25, 50, 75, 100.1],
                         labels=["Low", "Moderate", "High", "Severe"]).astype(str)
    return out.sort_values("index", ascending=False).reset_index(drop=True)


# 5. page chrome and shared UI helpers

st.set_page_config(page_title="Kenya Climate Variability · Group 3",
                   page_icon=":material/insights:", layout="wide", initial_sidebar_state="expanded")

st.markdown(f"""
<style>
  .stApp {{ background: {PLANE}; }}
  .block-container {{ padding-top: 3rem; max-width: 1500px; }}
  h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.01em; }}
  .masthead {{ border-left: 3px solid {SERIES[0]}; padding: 0.1rem 0 0.1rem 1rem; margin-bottom: 0.4rem; }}
  .masthead .kicker {{ font-size: 0.74rem; letter-spacing: 0.13em; text-transform: uppercase;
                       color: {MUTED}; font-weight: 600; }}
  .masthead h1 {{ font-size: 1.85rem; margin: 0.15rem 0 0.2rem 0; }}
  .masthead p {{ color: {INK_2}; margin: 0; font-size: 0.94rem; }}
  .qcard {{ background: {SURFACE}; border: 1px solid rgba(11,11,11,0.10); border-radius: 10px;
            padding: 1rem 1.15rem; margin: 0.2rem 0 1.1rem 0; }}
  .qcard .qlabel {{ font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase;
                    color: {SERIES[0]}; font-weight: 700; }}
  .qcard .qtext {{ color: {INK}; font-size: 1.05rem; font-weight: 600; margin-top: 0.2rem; }}
  .qcard .qwhy {{ color: {INK_2}; font-size: 0.88rem; margin-top: 0.45rem; }}
  .finding {{ background: rgba(42,120,214,0.06); border-left: 3px solid {SERIES[0]};
              border-radius: 0 8px 8px 0; padding: 0.7rem 0.95rem; margin: 0.25rem 0 0.9rem 0;
              color: {INK}; font-size: 0.92rem; line-height: 1.5; }}
  .caveat {{ background: rgba(250,178,25,0.10); border-left: 3px solid #fab219;
             border-radius: 0 8px 8px 0; padding: 0.7rem 0.95rem; margin: 0.25rem 0 0.9rem 0;
             color: {INK}; font-size: 0.9rem; }}
  div[data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid rgba(11,11,11,0.10);
                                 border-radius: 10px; padding: 0.85rem 1rem; }}
  div[data-testid="stMetricLabel"] p {{ font-size: 0.76rem !important; letter-spacing: 0.05em;
                                        text-transform: uppercase; color: {MUTED} !important;
                                        font-weight: 600; }}
  div[data-testid="stMetricValue"] {{ color: {INK}; font-size: 1.65rem; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 0.15rem; border-bottom: 1px solid {GRID}; }}
  .stTabs [data-baseweb="tab"] {{ font-size: 0.9rem; font-weight: 600; color: {INK_2}; }}
  section[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {GRID}; }}
  .legend-chip {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px;
                  font-size: 0.78rem; font-weight: 600; margin-right: 0.3rem; }}
</style>
""", unsafe_allow_html=True)


def question_card(number: str, question: str, why: str) -> None:
    """Print the research question a section answers, and why the chart form fits."""
    st.markdown(
        f'<div class="qcard"><div class="qlabel">Research question {number}</div>'
        f'<div class="qtext">{question}</div><div class="qwhy">{why}</div></div>',
        unsafe_allow_html=True,
    )


def chart_block(fig: go.Figure, *, key: str, finding: str,
                table: pd.DataFrame | None = None, caveat: str | None = None,
                height: int | None = None) -> None:
    """
    Render a chart with the evidence sentence it supports and the numbers
    behind it (which is also the accessibility fallback for colour).
    """
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key)
    st.markdown(f'<div class="finding">{finding}</div>', unsafe_allow_html=True)
    if caveat:
        st.markdown(f'<div class="caveat">{caveat}</div>', unsafe_allow_html=True)
    if table is not None:
        with st.expander("Table view — the numbers behind this chart"):
            st.dataframe(table, width="stretch", hide_index=True)
            st.download_button("Download this table (CSV)",
                               table.to_csv(index=False).encode(),
                               file_name=f"{key}.csv", key=f"dl_{key}")


def month_axis(fig: go.Figure) -> go.Figure:
    """Label a 1–12 month axis with abbreviations instead of bare numbers."""
    fig.update_xaxes(tickmode="array", tickvals=list(range(1, 13)),
                     ticktext=[calendar.month_abbr[m] for m in range(1, 13)])
    return fig


def ramp(colors: list[str]) -> list[list]:
    """Turn a list of hex steps into a Plotly colorscale."""
    return [[i / (len(colors) - 1), c] for i, c in enumerate(colors)]


def labelled_heatmap(z, x, y, labels, *, colorscale, hovertemplate, colorbar_title,
                     zmin=None, zmax=None, zmid=None) -> go.Figure:
    """
    A heatmap whose every cell prints its own value.

    Cell labels are drawn as annotations rather than with `texttemplate` for one
    reason: the ink has to flip to white on the dark end of the ramp. A single
    uniform label colour is unreadable at one end or the other, and an
    unreadable label defeats the point of labelling — the labels are what let a
    reader who cannot separate the colours still read the matrix.
    """
    z = np.asarray(z, dtype=float)
    fig = go.Figure(go.Heatmap(
        z=z, x=list(x), y=list(y), colorscale=colorscale, xgap=2, ygap=2,
        zmin=zmin, zmax=zmax, zmid=zmid, hovertemplate=hovertemplate,
        colorbar=dict(title=dict(text=colorbar_title, side="top"), thickness=12,
                      len=0.78, outlinewidth=0, x=1.015,
                      tickfont=dict(color=MUTED, size=11))))
    lo = np.nanmin(z) if zmin is None else zmin
    hi = np.nanmax(z) if zmax is None else zmax
    span = max(abs(lo), abs(hi)) if zmid is not None else (hi - lo)
    for i, yv in enumerate(y):
        for j, xv in enumerate(x):
            v = z[i, j]
            if np.isnan(v):
                continue
            weight = abs(v) / span if zmid is not None else (v - lo) / (span or 1)
            fig.add_annotation(x=xv, y=yv, text=labels[i][j], showarrow=False,
                               font=dict(size=11,
                                         color="#ffffff" if weight > 0.62 else INK))
    # The axis type is left to Plotly's own detection: forcing "category" breaks
    # numeric-looking labels such as years, which it reads as a linear scale.
    fig.update_yaxes(autorange="reversed")
    return fig


# 6. load data and sidebar filters

data, quality = load_data()

with st.sidebar:
    st.markdown("### Filters")
    st.caption("Every KPI, chart and table on the page responds to these controls.")

    counties = st.multiselect(
        "Counties", list(LOCATIONS), default=list(LOCATIONS),
        help="Compare any subset of the six stations.",
    )
    if not counties:
        st.warning("Select at least one county.")
        st.stop()

    year_range = st.slider("Study period", 2015, 2024, (2015, 2024), step=1,
                           help="The API archive covers 2015–2024 (ten complete years).")
    if year_range[1] - year_range[0] + 1 < 3:
        st.error("Select at least three years. Trend fitting, variability and the "
                 "confidence intervals on the Q3 tab are undefined on a shorter "
                 "window, and a dashboard that quietly returns a number anyway "
                 "would be worse than one that refuses.")
        st.stop()

    st.markdown("---")
    st.markdown("### Analysis settings")
    dry_threshold = st.slider(
        "Dry-day threshold (mm)", 0.0, 5.0, DRY_DAY_DEFAULT, 0.5,
        help="A day with less rainfall than this counts as dry. 1 mm is the "
             "conventional meteorological cut-off; raise it to test how "
             "sensitive the drought findings are to the definition.",
    )
    min_spell = st.slider("Show dry spells of at least (days)", 7, 60, 21, 7,
                          help="Controls the dry-spell timeline on the Drought Risk tab.")
    smooth_days = st.select_slider("Daily-series smoothing (days)",
                                   options=[1, 7, 30, 90, 365], value=30,
                                   help="Rolling mean applied in the County Deep Dive.")

    st.markdown("---")
    st.markdown("### Counties on screen")
    for loc in counties:
        st.markdown(
            f'<span class="legend-chip" style="background:{COUNTY_COLOR[loc]}1f;'
            f'color:{INK};border:1px solid {COUNTY_COLOR[loc]}">{loc}</span>',
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.caption("**Source** Open-Meteo Historical Weather (ERA5) Archive API · "
               "daily values, `Africa/Nairobi` timezone · 6 stations × 3,653 days.")

# The filtered frame every downstream computation uses.
df = data[data.location.isin(counties) &
          data.year.between(*year_range)].copy()
ordered = [c for c in LOCATIONS if c in counties]      # keeps colour assignment stable

# Pre-compute the analytics once per interaction.
temp_year = annual_temperature(df)
rain_year = annual_rainfall(df)
rain_var = rainfall_variability(df)
trends = temperature_trends(df)
clim = monthly_climatology(df)
spells = dry_spells(df, dry_threshold)
vuln = vulnerability(df, dry_threshold)

# Headline numbers reused across tabs.
temp_rank = temp_year.groupby("location").mean_temp.mean().sort_values(ascending=False)
hottest, hottest_c = temp_rank.index[0], temp_rank.iloc[0]
peak_year_row = temp_year.loc[temp_year.mean_temp.idxmax()]
most_variable = rain_var.iloc[0]
longest = spells.iloc[0] if not spells.empty else None
n_significant = int(trends.significant.sum())
national_month = clim.groupby(["month", "month_name"], as_index=False).mm_per_month.mean()
wettest_month = national_month.loc[national_month.mm_per_month.idxmax()]
top_risk = vuln.iloc[0]

multi = len(ordered) > 1
coolest, coolest_c = temp_rank.index[-1], temp_rank.iloc[-1]
least_variable = rain_var.iloc[-1]
runner_temp = (f", ahead of {temp_rank.index[1]} ({temp_rank.iloc[1]:.1f} °C). "
               f"The coolest station on screen, {coolest} ({coolest_c:.1f} °C), sits "
               f"about {hottest_c - coolest_c:.1f} °C lower"
               if multi else " (the only county on screen)")
runner_rain = (f" {rain_var.iloc[1].location} is next at "
               f"CV {rain_var.iloc[1].cv_pct:.1f}%, but from a much wetter base "
               f"({rain_var.iloc[1].mean_mm:.0f} mm), so the same percentage swing is "
               f"far less likely to empty a reservoir." if multi else "")
runner_vuln = (f" The gap to second place ({vuln.iloc[1].location}, "
               f"{vuln.iloc[1]['index']:.0f}) is the clearest signal in this entire "
               f"dashboard." if multi else "")

# 7. KPI cards

st.markdown(f"""
<div class="masthead">
  <div class="kicker">Kenya Meteorological Department · Consulting brief · Group 3</div>
  <h1>Historical Weather &amp; Climate Variability in Kenya</h1>
  <p>Ten years of daily observations for six county stations, {year_range[0]}–{year_range[1]},
     read for one purpose: where should counties spend scarce adaptation money first?</p>
</div>
""", unsafe_allow_html=True)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Hottest county", hottest, f"{hottest_c:.1f} °C decade average",
          delta_color="off", delta_arrow="off", icon=":material/device_thermostat:", border=False,
          help="Mean of the ten annual mean temperatures.")
k2.metric("Most erratic rainfall", most_variable.location,
          f"CV {most_variable.cv_pct:.1f}% year to year", delta_color="off", delta_arrow="off",
          icon=":material/water_drop:", border=False,
          help="Coefficient of variation of annual rainfall totals — "
               "standard deviation as a percentage of the mean.")
k3.metric("Longest dry spell",
          f"{int(longest.days) if longest is not None else 0} days",
          f"{longest.location} · from {longest.start:%b %Y}" if longest is not None else "—",
          delta_color="off", delta_arrow="off", icon=":material/wb_sunny:", border=False,
          help=f"Longest unbroken run of days below {dry_threshold:g} mm of rainfall.")
k4.metric("Warming trends", f"{n_significant} of {len(trends)}",
          "counties at p < 0.05", delta_color="off", delta_arrow="off",
          icon=":material/trending_up:", border=False,
          help="Ordinary least squares trend of annual mean temperature on year.")
k5.metric("Highest drought risk", top_risk.location,
          f"{top_risk.tier} · index {top_risk['index']:.0f}/100",
          delta_color="off", delta_arrow="off", icon=":material/priority_high:", border=False,
          help="Composite of aridity, rainfall variability, dry-spell persistence and heat.")

tabs = st.tabs([
    "Executive summary",
    "Q1 · Temperature",
    "Q2 · Rainfall variability",
    "Q3 · Warming trends",
    "Q4 · Seasonality",
    "Q5 · Drought risk",
    "County deep dive",
    "Data & method",
])


# Tab 0 = Executive summary and geographic map
with tabs[0]:
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        st.markdown("#### Where the six stations sit, and how exposed each one is")
        map_metric = st.radio(
            "Colour the map by", ["Drought-risk tier", "Mean temperature",
                                  "Mean annual rainfall", "Longest dry spell"],
            horizontal=True, label_visibility="collapsed", key="map_metric",
        )

        geo = vuln.merge(pd.DataFrame(
            [{"location": k, "lat": v[0], "lon": v[1]} for k, v in LOCATIONS.items()]),
            on="location")
        geo = geo.merge(temp_rank.rename("temp").reset_index(), on="location")

        hover = (
            "<b>%{customdata[0]}</b><br>"
            "Mean temperature: %{customdata[1]:.1f} °C<br>"
            "Mean annual rainfall: %{customdata[2]:.0f} mm<br>"
            "Rainfall variability (CV): %{customdata[3]:.1f}%<br>"
            "Longest dry spell: %{customdata[4]:.0f} days<br>"
            "Drought-risk index: %{customdata[5]:.0f}/100 (%{customdata[6]})"
            "<extra></extra>"
        )
        custom = geo[["location", "temp", "mean_mm", "cv_pct",
                      "longest_dry_days", "index", "tier"]].values

        # Bubble area encodes mean annual rainfall in every view; colour encodes
        # whichever measure the reader picked. Two channels, two measures — no
        # second y-axis anywhere.
        # The size floor is deliberately generous: the driest county is also the
        # highest-risk one, and it must not end up as the least visible mark.
        size = 20 + 30 * (geo.mean_mm - geo.mean_mm.min()) / max(
            geo.mean_mm.max() - geo.mean_mm.min(), 1e-9)

        fig = go.Figure()
        if map_metric == "Drought-risk tier":
            for tier in ["Severe", "High", "Moderate", "Low"]:
                sub = geo[geo.tier == tier]
                if sub.empty:
                    continue
                idx = geo.tier == tier
                fig.add_trace(go.Scattergeo(
                    lon=sub.lon, lat=sub.lat, name=tier,
                    mode="markers+text", text=sub.location,
                    textposition="middle right", textfont=dict(color=INK, size=12),
                    marker=dict(size=size[idx], color=STATUS[tier], opacity=0.9,
                                line=dict(width=2, color=SURFACE)),
                    customdata=custom[idx.values], hovertemplate=hover,
                ))
        else:
            col, unit, ramp_title = {
                "Mean temperature": ("temp", "°C", "Mean temp (°C)"),
                "Mean annual rainfall": ("mean_mm", "mm", "Rainfall (mm)"),
                "Longest dry spell": ("longest_dry_days", "days", "Dry spell (days)"),
            }[map_metric]
            fig.add_trace(go.Scattergeo(
                lon=geo.lon, lat=geo.lat, mode="markers+text", text=geo.location,
                textposition="middle right", textfont=dict(color=INK, size=12),
                marker=dict(size=size, color=geo[col],
                            colorscale=[[i / (len(SEQ_BLUE) - 1), c]
                                        for i, c in enumerate(SEQ_BLUE)],
                            line=dict(width=2, color=SURFACE),
                            colorbar=dict(title=dict(text=ramp_title, side="right"),
                                          thickness=12, len=0.6, outlinewidth=0,
                                          tickfont=dict(color=MUTED))),
                customdata=custom, hovertemplate=hover, showlegend=False,
            ))

        fig.update_geos(
            scope="africa", resolution=50,
            lataxis_range=[-5.6, 2.2], lonaxis_range=[32.8, 42.4],
            showcountries=True, countrycolor=AXIS, countrywidth=1,
            showsubunits=True, subunitcolor=GRID,
            showland=True, landcolor="#f2f1ec",
            showocean=True, oceancolor="#e8eef5",
            showlakes=True, lakecolor="#dbe7f3",
            coastlinecolor=AXIS, bgcolor=SURFACE,
        )
        fig.update_layout(height=430, margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", y=-0.02, x=0))
        event = st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG,
                                key="map", on_select="rerun", selection_mode="points")

        # Drill-down: clicking a bubble sets the county used by the deep-dive tab.
        picked = None
        try:
            pts = event["selection"]["points"]
            if pts:
                picked = pts[0]["customdata"][0]
        except (TypeError, KeyError, IndexError):
            picked = None
        if picked:
            st.session_state["drill_county"] = picked
            st.success(f"**{picked}** selected — open the **County deep dive** tab "
                       f"for its daily record.", icon=":material/touch_app:")

        st.caption("Bubble area is average annual rainfall. Click a bubble to drill "
                   "into that county.")

    with right:
        st.markdown("#### Executive summary")
        st.markdown(f"""
* Kenya's climate problem in this record is not a decade of warming, instead, 
it is **where the rain falls and how reliably**, and on that measure
**{top_risk.location}** is in a category of its own.

1. **{hottest} is the hottest station** at **{hottest_c:.1f} °C** averaged over the
   period, peaking at **{peak_year_row.mean_temp:.1f} °C in {int(peak_year_row.year)}**{
   f" — about **{hottest_c - coolest_c:.1f} °C** warmer than {coolest}, the coolest station"
   if multi else ""}.
2. **{most_variable.location} has the least dependable rainfall**: a coefficient of
   variation of **{most_variable.cv_pct:.1f}%**, swinging between
   **{most_variable.min_mm:.0f} mm** and **{most_variable.max_mm:.0f} mm** a year.
   Planning to an average is planning to a number that rarely happens.
3. **No station shows statistically significant warming over these ten years**
   ({n_significant} of {len(trends)} at p&nbsp;<&nbsp;0.05). Ten annual points is a
   short series — this is a statement about the evidence available, not proof that
   Kenya is not warming.
4. **Rainfall is strongly seasonal and bimodal**: **{wettest_month.month_name}** is the
   wettest month nationally (**{wettest_month.mm_per_month:.0f} mm** on average),
   with a second peak in the October–December short rains.
5. **{top_risk.location} carries the highest composite drought risk**
   ({top_risk['index']:.0f}/100): the lowest rainfall
   (**{top_risk.mean_mm:.0f} mm**), the highest variability
   (**{top_risk.cv_pct:.1f}%**), the longest dry spell
   (**{int(top_risk.longest_dry_days)} days**) and the highest temperature
   (**{top_risk.mean_temp:.1f} °C**) — all four strands point the same way.
        """)

        st.markdown("##### What follows for the client")
        st.markdown(f"""
- **Fund water storage where rainfall is erratic, not merely where it is low.**
  {most_variable.location}'s CV of {most_variable.cv_pct:.1f}% means storage sized to
  the mean will fail in the dry tail.
- **Design {top_risk.location}'s water systems for a
  {int(top_risk.longest_dry_days)}-day no-rain window**, because that is what the
  record contains.
- **Put flood readiness on a calendar**: drainage and early warning staffed before
  {wettest_month.month_name}, storage filled during it.
- **Keep monitoring temperature rather than declaring a trend.** The ten-year test is
  underpowered; the reporting line should be the interval, not the slope.
        """)

# Tab 1 = Q1 Temperature
with tabs[1]:
    question_card(
        "1", "Which location recorded the highest average annual temperature "
             "during the study period?",
        "A range-dot plot shows the average daily minimum and maximum for each county, "
        "with the ten-year mean overlaid. A heatmap shows the annual mean for each "
        "county-year, for one to see both the long-term average and the year-to-year variation."
        )

    v1, v2 = st.columns([1, 1], gap="large")

    with v1:
        rng = (temp_year.groupby("location")
                        .agg(mean_temp=("mean_temp", "mean"),
                             mean_max=("mean_max", "mean"),
                             mean_min=("mean_min", "mean"))
                        .reindex(temp_rank.index).reset_index())
        fig = go.Figure()
        # The range line first, so the mean marker reads as sitting on top of it.
        for _, r in rng.iterrows():
            fig.add_trace(go.Scatter(
                x=[r.mean_min, r.mean_max], y=[r.location, r.location],
                mode="lines", line=dict(color=GRID, width=8), showlegend=False,
                hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=rng.mean_min, y=rng.location, mode="markers", name="Avg daily minimum",
            marker=dict(size=11, color=SEQ_BLUE[2], line=dict(width=2, color=SURFACE)),
            hovertemplate="%{y} · average daily minimum %{x:.1f} °C<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=rng.mean_max, y=rng.location, mode="markers", name="Avg daily maximum",
            marker=dict(size=11, color="#e34948", line=dict(width=2, color=SURFACE)),
            hovertemplate="%{y} · average daily maximum %{x:.1f} °C<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=rng.mean_temp, y=rng.location, mode="markers", name="Annual mean",
            marker=dict(size=17, color=INK, symbol="diamond",
                        line=dict(width=2, color=SURFACE)),
            hovertemplate="%{y} · annual mean %{x:.1f} °C<extra></extra>"))
        # The mean is also printed in a right-aligned column: a label pinned to the
        # marker would collide with the maximum-temperature dot on the hot rows.
        for _, r in rng.iterrows():
            fig.add_annotation(x=45.5, y=r.location, text=f"<b>{r.mean_temp:.1f} °C</b>",
                               showarrow=False, xanchor="right",
                               font=dict(color=INK, size=12))
        fig.update_layout(
            title="Average temperature and the typical day, ranked",
            xaxis_title="Temperature (°C)", yaxis_title=None,
            yaxis=dict(autorange="reversed"),
            xaxis=dict(range=[8, 46], dtick=5), height=430,
            margin=dict(l=90, r=40, t=56, b=90))
        chart_block(
            fig, key="q1_range",
            finding=f"<b>{hottest}</b> is the hottest station at "
                    f"<b>{hottest_c:.1f} °C</b>{runner_temp}. Compare the bar "
                    f"<i>lengths</i> too: a wide range means cold nights as well as mild "
                    f"days — a different adaptation problem (crop frost risk, night-time "
                    f"heating) from the persistent, narrow-range heat at the top of the "
                    f"ranking, which is a public-health and water-demand problem.",
            table=rng.round(2).rename(columns={
                "location": "County", "mean_temp": "Annual mean (°C)",
                "mean_max": "Avg daily max (°C)", "mean_min": "Avg daily min (°C)"}))

    with v2:
        pivot = (temp_year.pivot(index="location", columns="year", values="mean_temp")
                          .reindex(temp_rank.index))
        fig = labelled_heatmap(
            pivot.values, pivot.columns, pivot.index,
            [[f"{v:.1f}" for v in row] for row in pivot.values],
            colorscale=ramp(SEQ_BLUE), colorbar_title="°C",
            hovertemplate="%{y} · %{x}<br>Annual mean %{z:.2f} °C<extra></extra>")
        fig.update_layout(title="Annual mean temperature, county × year",
                          xaxis_title="Year", yaxis_title=None, height=430,
                          xaxis=dict(dtick=1, showgrid=False),
                          margin=dict(l=90, r=80, t=56, b=90))
        chart_block(
            fig, key="q1_heat",
            finding=f"The hottest single county-year in the record is "
                    f"<b>{peak_year_row.location} in {int(peak_year_row.year)}</b> at "
                    f"<b>{peak_year_row.mean_temp:.2f} °C</b>. The rows are strongly "
                    f"banded — a county's climate zone dominates any year-to-year "
                    f"wobble, which is why adaptation planning has to be county-specific "
                    f"rather than national.",
            table=pivot.round(2).rename(columns=str).reset_index()
                       .rename(columns={"location": "County"}))

# Tab 2 = Q2 Rainfall variability
with tabs[2]:
    question_card(
        "2", "Which county experienced the greatest annual rainfall variability?",
        "Variability is a two-measure question — how much rain, and how unreliable — "
        "so the lead chart is a scatter with median reference lines rather than a bar "
        "chart of one statistic. Every point is directly labelled and drawn in a "
        "single hue: with six points, text identifies them better than six colours, "
        "and it keeps the chart inside the colour-safe limit for scatter forms.")

    st.markdown("##### The two questions a water engineer actually asks")
    fig = go.Figure()
    fig.add_vline(x=rain_var.mean_mm.median(), line=dict(color=GRID, width=1, dash="dash"))
    fig.add_hline(y=rain_var.cv_pct.median(), line=dict(color=GRID, width=1, dash="dash"))
    # Quadrant captions are pinned to the plot corners (paper coordinates), not to
    # data values, so they can never land on top of a county.
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.99,
                       text="<b>Dry and erratic</b><br>highest adaptation priority",
                       showarrow=False, xanchor="left", yanchor="top",
                       font=dict(color="#d03b3b", size=12), align="left")
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.01,
                       text="<b>Wet and dependable</b>", showarrow=False,
                       xanchor="right", yanchor="bottom",
                       font=dict(color="#0ca30c", size=12))
    fig.add_trace(go.Scatter(
        x=rain_var.mean_mm, y=rain_var.cv_pct, mode="markers+text",
        text=[f" {l}" for l in rain_var.location], textposition="middle right",
        textfont=dict(color=INK, size=13),
        marker=dict(size=10 + 22 * rain_var.sd_mm / rain_var.sd_mm.max(),
                    color=SERIES[0], opacity=0.85, line=dict(width=2, color=SURFACE)),
        customdata=rain_var[["location", "sd_mm", "min_mm", "max_mm"]].values,
        hovertemplate="<b>%{customdata[0]}</b><br>Mean %{x:.0f} mm/yr<br>"
                      "CV %{y:.1f}%<br>SD ±%{customdata[1]:.0f} mm<br>"
                      "Range %{customdata[2]:.0f}–%{customdata[3]:.0f} mm"
                      "<extra></extra>", showlegend=False))
    # Headroom above the highest point, so the corner captions land on empty
    # space instead of on a county.
    pad_x = max((rain_var.mean_mm.max() - rain_var.mean_mm.min()) * 0.22, 60)
    span_y = max(rain_var.cv_pct.max() - rain_var.cv_pct.min(), 5)
    fig.update_layout(
        title="Average annual rainfall versus its year-to-year variability",
        xaxis_title="Mean annual rainfall (mm) →  wetter",
        yaxis_title="Coefficient of variation (%) →  less dependable",
        xaxis=dict(range=[rain_var.mean_mm.min() - pad_x * 0.5,
                          rain_var.mean_mm.max() + pad_x]),
        yaxis=dict(range=[rain_var.cv_pct.min() - span_y * 0.18,
                          rain_var.cv_pct.max() + span_y * 0.38]),
        height=440, margin=dict(l=70, r=40, t=56, b=60))
    chart_block(
        fig, key="q2_quadrant",
        finding=f"<b>{most_variable.location}</b> has the greatest variability at "
                f"<b>CV {most_variable.cv_pct:.1f}%</b> "
                f"(±{most_variable.sd_mm:.0f} mm on a mean of "
                f"{most_variable.mean_mm:.0f} mm) and sits alone in the dry-and-erratic "
                f"quadrant.{runner_rain}",
        caveat="CV is used rather than raw standard deviation because the counties have "
               "very different rainfall totals — a ±450 mm swing is routine in Mombasa "
               "and catastrophic in Garissa. Both are in the table below.",
        table=rain_var.round(2).rename(columns={
            "location": "County", "mean_mm": "Mean annual (mm)", "sd_mm": "SD (mm)",
            "min_mm": "Driest year (mm)", "max_mm": "Wettest year (mm)",
            "cv_pct": "CV (%)"}))

    c1, c2 = st.columns([1, 1.25], gap="large")

    with c1:
        fig = go.Figure()
        for loc in ordered:
            sub = rain_year[rain_year.location == loc]
            fig.add_trace(go.Box(
                y=sub.rain, name=loc, boxpoints="all", jitter=0.5, pointpos=0,
                marker=dict(size=7, color=COUNTY_COLOR[loc],
                            line=dict(width=1, color=SURFACE)),
                line=dict(color=COUNTY_COLOR[loc], width=2),
                fillcolor="rgba(0,0,0,0)", showlegend=False,
                customdata=sub[["year"]].values,
                hovertemplate="%{x} · %{customdata[0]}<br>%{y:.0f} mm<extra></extra>"))
        fig.update_layout(title="Distribution of the ten annual totals",
                          yaxis_title="Annual rainfall (mm)", xaxis_title=None,
                          height=420)
        chart_block(
            fig, key="q2_box",
            finding=(f"Variability is not the same shape everywhere: "
                     f"{most_variable.location}'s years are spread wide "
                     f"(CV {most_variable.cv_pct:.1f}%) while {least_variable.location} "
                     f"clusters tightly (CV {least_variable.cv_pct:.1f}%). "
                     if multi else
                     f"{most_variable.location}'s ten annual totals span "
                     f"{most_variable.min_mm:.0f}–{most_variable.max_mm:.0f} mm. ") +
                    "A tight box means an average is a usable planning number; a wide "
                    "one means budgeting to the average will under-deliver in roughly "
                    "half of all years.",
            table=rain_year.pivot(index="year", columns="location", values="rain")
                           .round(0).reset_index())

    with c2:
        piv = (rain_year.pivot(index="location", columns="year", values="anomaly_pct")
                        .reindex(ordered))
        lim = float(np.nanmax(np.abs(piv.values))) if piv.size else 50
        fig = labelled_heatmap(
            piv.values, piv.columns, piv.index,
            [[f"{v:+.0f}%" for v in row] for row in piv.values],
            colorscale=DIV_RAIN, zmid=0, zmin=-lim, zmax=lim,
            colorbar_title="vs own<br>average",
            hovertemplate="%{y} · %{x}<br>%{z:+.1f}% vs its own average<extra></extra>")
        fig.update_layout(title="Rainfall anomaly: each year against that county's own average",
                          xaxis_title="Year", yaxis_title=None, height=430,
                          xaxis=dict(dtick=1, showgrid=False),
                          margin=dict(l=90, r=90, t=56, b=60))
        worst = rain_year.loc[rain_year.anomaly_pct.idxmin()]
        chart_block(
            fig, key="q2_anom",
            finding=f"The deepest single-year deficit is <b>{worst.location} in "
                    f"{int(worst.year)}</b> at <b>{worst.anomaly_pct:+.0f}%</b> "
                    f"(z = {worst.z:+.1f}). Look for red columns spanning several rows: "
                    f"those are the years drought hit multiple counties at once, which is "
                    f"exactly when a national response — not a county one — is needed.",
            table=rain_year.round(1).rename(columns={
                "location": "County", "year": "Year", "rain": "Total (mm)",
                "local_mean": "County average (mm)", "anomaly_pct": "Anomaly (%)",
                "z": "Standardised (z)"}))

# Tab 3 = Q3 Warming trends
with tabs[3]:
    question_card(
        "3", "Have average temperatures increased significantly over the past ten years?",
        "This is a change-over-time question <i>and</i> a question about certainty, so "
        "it needs two charts. Lines with fitted trends show the direction; a "
        "coefficient plot with 95% confidence intervals shows whether the direction "
        "can be distinguished from noise. A bar chart of slopes would have implied "
        "precision the data does not support.")

    t1, t2 = st.columns([1.35, 1], gap="large")

    with t1:
        show_fit = st.toggle("Overlay fitted trend lines", value=True, key="q3_fit")
        fig = go.Figure()
        for loc in ordered:
            sub = temp_year[temp_year.location == loc].sort_values("year")
            fig.add_trace(go.Scatter(
                x=sub.year, y=sub.mean_temp, name=loc, mode="lines+markers",
                line=dict(color=COUNTY_COLOR[loc], width=2),
                marker=dict(size=8, color=COUNTY_COLOR[loc],
                            line=dict(width=2, color=SURFACE)),
                hovertemplate=f"<b>{loc}</b> · %{{x}}<br>%{{y:.2f}} °C<extra></extra>"))
            if show_fit and len(sub) > 2:
                fit = stats.linregress(sub.year, sub.mean_temp)
                fig.add_trace(go.Scatter(
                    x=sub.year, y=fit.intercept + fit.slope * sub.year,
                    mode="lines", line=dict(color=COUNTY_COLOR[loc], width=1, dash="dot"),
                    showlegend=False, hoverinfo="skip"))
            # Direct end-label, so identity survives without colour matching.
            fig.add_annotation(x=sub.year.iloc[-1], y=sub.mean_temp.iloc[-1],
                               text=f"  {loc}", showarrow=False, xanchor="left",
                               font=dict(color=INK_2, size=11))
        years_on_axis = list(range(year_range[0], year_range[1] + 1))
        fig.update_layout(title="Annual mean temperature by county, with fitted trend",
                          xaxis_title="Year", yaxis_title="Annual mean temperature (°C)",
                          height=470, margin=dict(l=70, r=95, t=56, b=95),
                          xaxis=dict(tickmode="array", tickvals=years_on_axis,
                                     range=[year_range[0] - 0.3,
                                            year_range[1] + 1.4]))
        chart_block(
            fig, key="q3_lines",
            finding="The lines are close to flat and the bands they occupy never cross: "
                    "counties keep their rank throughout. Year-to-year wobble (the "
                    "2016–17 and 2021–22 El Niño/La Niña swings) is larger than any "
                    "underlying drift, which is precisely why the significance test on "
                    "the right matters.",
            table=temp_year.round(2).rename(columns={
                "location": "County", "year": "Year", "mean_temp": "Annual mean (°C)",
                "mean_max": "Avg max (°C)", "mean_min": "Avg min (°C)"}))

    with t2:
        tr = trends.sort_values("per_decade")
        fig = go.Figure()
        fig.add_vline(x=0, line=dict(color=INK_2, width=1.5))
        fig.add_trace(go.Scatter(
            x=tr.per_decade, y=tr.location, mode="markers",
            error_x=dict(type="data", symmetric=False,
                         array=tr.ci_high - tr.per_decade,
                         arrayminus=tr.per_decade - tr.ci_low,
                         color=AXIS, thickness=2, width=6),
            marker=dict(size=13, color=SERIES[0], line=dict(width=2, color=SURFACE)),
            customdata=tr[["p_value", "r_squared", "n_years"]].values,
            hovertemplate="<b>%{y}</b><br>%{x:+.2f} °C per decade<br>"
                          "p = %{customdata[0]:.3f} · R² = %{customdata[1]:.2f} "
                          "· n = %{customdata[2]} years<extra></extra>",
            showlegend=False))
        for _, r in tr.iterrows():
            fig.add_annotation(x=r.ci_high, y=r.location,
                               text=f"  p = {r.p_value:.2f}", showarrow=False,
                               xanchor="left", font=dict(color=MUTED, size=11))
        fig.update_layout(title="Warming rate with 95% confidence interval",
                          xaxis_title="°C per decade", yaxis_title=None, height=460,
                          margin=dict(l=90, r=95, t=56, b=56))
        chart_block(
            fig, key="q3_forest",
            finding=f"Every interval crosses zero: <b>{n_significant} of {len(trends)} "
                    f"counties show a statistically significant trend</b> at p < 0.05. "
                    f"The strongest signal is {tr.iloc[0].location} at "
                    f"{tr.iloc[0].per_decade:+.2f} °C/decade (p = "
                    f"{tr.iloc[0].p_value:.3f}), which is suggestive but not conclusive.",
            caveat="Ten annual points is a short series; a decade of data has low "
                   "statistical power to detect the ~0.2 °C/decade warming reported in "
                   "longer Kenyan records. The correct reading is <i>“this record does "
                   "not establish a trend”</i>, not <i>“there is no warming”</i>. "
                   "Recommendation: keep monitoring and re-test on a 30-year window.",
            table=trends.round(4).rename(columns={
                "location": "County", "slope_per_year": "Slope (°C/yr)",
                "per_decade": "°C per decade", "ci_low": "CI low", "ci_high": "CI high",
                "r_squared": "R²", "p_value": "p-value", "n_years": "Years",
                "significant": "Significant (p<0.05)"}))

# Tab 4 = Q4 Rainfall seasonality
with tabs[4]:
    question_card(
        "4", "Which months consistently record the highest rainfall across the "
             "selected locations?",
        "“Consistently, across locations” is a pattern-across-two-categories question, "
        "and the form built for that is a heatmap: twelve months × six counties in one "
        "read, where a vertical dark band <i>is</i> the answer. The national profile "
        "beside it collapses the same data to one axis for the headline, and the "
        "cumulative curve answers the follow-up planners always ask — <i>when</i> does "
        "the water actually arrive?")

    s1, s2 = st.columns([1.3, 1], gap="large")

    with s1:
        piv = (clim.pivot(index="location", columns="month", values="mm_per_month")
                   .reindex(ordered))
        fig = labelled_heatmap(
            piv.values, [calendar.month_abbr[m] for m in piv.columns], piv.index,
            [[f"{v:.0f}" for v in row] for row in piv.values],
            colorscale=ramp(SEQ_BLUE), colorbar_title="mm per<br>month",
            hovertemplate="%{y} · %{x}<br>%{z:.0f} mm in an average month<extra></extra>")
        fig.update_layout(title="Rainfall climatology: average millimetres per calendar month",
                          xaxis_title=None, yaxis_title=None, height=400,
                          margin=dict(l=90, r=95, t=56, b=40))
        peak_per_loc = clim.loc[clim.groupby("location").mm_per_month.idxmax()]
        mode_month = peak_per_loc.month_name.value_counts()
        off_peak = [f"<b>{r.location}</b> peaks in {r.month_name}"
                    for _, r in peak_per_loc.iterrows()
                    if r.month_name != wettest_month.month_name]
        seasonal_caveat = (
            f"The pattern is not universal: {', '.join(off_peak)}. A county whose "
            f"wettest month falls in the October–December <i>short</i> rains depends on "
            f"a different season entirely, so a national April-focused readiness "
            f"calendar would leave it exposed at exactly the wrong time of year."
            if off_peak else
            "Every county on screen peaks in the same month, so a single readiness "
            "calendar fits them all — but re-check this after changing the county "
            "selection, because the six stations do not all share one peak.")
        chart_block(
            fig, key="q4_heat",
            finding=f"Two dark bands appear — <b>March–May (long rains)</b> and "
                    f"<b>October–December (short rains)</b> — separated by a dry "
                    f"January–February and a dry June–September in the east. "
                    f"<b>{wettest_month.month_name}</b> is the wettest month nationally "
                    f"at {wettest_month.mm_per_month:.0f} mm, and it is the single "
                    f"wettest month in <b>{int(mode_month.iloc[0])} of "
                    f"{len(peak_per_loc)}</b> counties.",
            caveat=seasonal_caveat,
            table=piv.round(0).rename(columns={m: calendar.month_abbr[m]
                                               for m in piv.columns})
                     .reset_index().rename(columns={"location": "County"}))

    with s2:
        nat = national_month.sort_values("month")
        colors = [SERIES[0] if m in (3, 4, 5) else
                  SEQ_BLUE[3] if m in (10, 11, 12) else AXIS for m in nat.month]
        fig = go.Figure(go.Bar(
            x=nat.month, y=nat.mm_per_month,
            marker=dict(color=colors, line=dict(width=0), cornerradius=4),
            width=0.62,
            text=[f"{v:.0f}" for v in nat.mm_per_month], textposition="outside",
            textfont=dict(color=INK_2, size=11), cliponaxis=False,
            hovertemplate="%{customdata}<br>%{y:.0f} mm averaged across counties"
                          "<extra></extra>",
            customdata=[calendar.month_name[m] for m in nat.month]))
        fig.add_annotation(x=4, y=nat.mm_per_month.max() * 1.16, text="<b>Long rains</b>",
                           showarrow=False, font=dict(color=SERIES[0], size=12))
        fig.add_annotation(x=11, y=nat.mm_per_month.max() * 1.16, text="<b>Short rains</b>",
                           showarrow=False, font=dict(color=SEQ_BLUE[4], size=12))
        fig.update_layout(title="National monthly profile (mean of counties on screen)",
                          yaxis_title="Rainfall (mm per month)", xaxis_title=None,
                          height=400, showlegend=False,
                          yaxis=dict(range=[0, nat.mm_per_month.max() * 1.3]))
        month_axis(fig)
        chart_block(
            fig, key="q4_bars",
            finding=f"The profile is textbook bimodal: a tall {wettest_month.month_name} "
                    f"peak, a secondary November peak, and two reliably dry windows "
                    f"(Jan–Feb and Jun–Sep). Roughly "
                    f"{100 * nat[nat.month.isin([3,4,5,10,11,12])].mm_per_month.sum() / nat.mm_per_month.sum():.0f}% "
                    f"of the year's rain falls in those six season months — so half the "
                    f"calendar delivers most of the water.",
            table=nat[["month_name", "mm_per_month"]].round(1).rename(columns={
                "month_name": "Month", "mm_per_month": "Mean rainfall (mm)"}))

    st.markdown("##### When in the year does the water actually arrive?")
    fig = go.Figure()
    for loc in ordered:
        sub = (df[df.location == loc].groupby("doy", as_index=False)
                 .precipitation_sum.mean().sort_values("doy"))
        sub["cum"] = sub.precipitation_sum.cumsum()
        fig.add_trace(go.Scatter(
            x=sub.doy, y=sub.cum, name=loc, mode="lines",
            line=dict(color=COUNTY_COLOR[loc], width=2),
            hovertemplate=f"<b>{loc}</b> · day %{{x}}<br>%{{y:.0f}} mm "
                          f"accumulated<extra></extra>"))
        fig.add_annotation(x=sub.doy.iloc[-1], y=sub.cum.iloc[-1], text=f"  {loc}",
                           showarrow=False, xanchor="left",
                           font=dict(color=INK_2, size=11))
    fig.update_layout(
        title="Cumulative rainfall through an average year",
        xaxis=dict(title=None, tickmode="array",
                   tickvals=[1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335],
                   ticktext=[calendar.month_abbr[m] for m in range(1, 13)],
                   range=[0, 400]),
        yaxis_title="Accumulated rainfall (mm)", height=420,
        margin=dict(l=70, r=95, t=56, b=90))
    steep = clim.groupby("month").mm_per_month.sum().idxmax()
    chart_block(
        fig, key="q4_cum",
        finding=f"The lines share a staircase shape — steep through "
                f"{calendar.month_name[steep]}, flat through the dry season — but their "
                f"heights differ threefold. The flat stretches are the operational "
                f"problem: a county that receives nothing for four months needs storage "
                f"that spans four months, regardless of its annual total.",
        table=None)

# Tab 5 = Q5 Drought vulnerability
with tabs[5]:
    question_card(
        "5", "Which counties appear most vulnerable to drought or prolonged dry periods?",
        "Vulnerability is not a measured variable — it has to be constructed from "
        "several, so the visualisation must show the construction, not just the "
        "verdict. A ranked index bar answers “who”, the component matrix beside it "
        "shows “on what grounds”, and the dry-spell timeline shows the raw evidence in "
        "its original units so a reader can audit the index rather than trust it.")

    r1, r2 = st.columns([1, 1.15], gap="large")

    with r1:
        v = vuln.sort_values("index")
        fig = go.Figure(go.Bar(
            x=v["index"], y=v.location, orientation="h", width=0.6,
            marker=dict(color=[STATUS[t] for t in v.tier], line=dict(width=0),
                        cornerradius=4),
            text=[f"{i:.0f} · {t}" for i, t in zip(v["index"], v.tier)],
            textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False,
            customdata=v[["mean_mm", "cv_pct", "longest_dry_days", "mean_temp", "tier"]].values,
            hovertemplate="<b>%{y}</b> — %{customdata[4]} risk<br>"
                          "Index %{x:.0f}/100<br>Rainfall %{customdata[0]:.0f} mm/yr<br>"
                          "CV %{customdata[1]:.1f}%<br>"
                          "Longest dry spell %{customdata[2]:.0f} days<br>"
                          "Mean temp %{customdata[3]:.1f} °C<extra></extra>"))
        fig.update_layout(title="Composite drought-vulnerability index",
                          xaxis_title="Index (0–100, relative to counties on screen)",
                          yaxis_title=None, height=400, xaxis=dict(range=[0, 118]),
                          margin=dict(l=90, r=40, t=56, b=50))
        chart_block(
            fig, key="q5_index",
            finding=f"<b>{top_risk.location} scores {top_risk['index']:.0f}/100 "
                    f"({top_risk.tier})</b> — the top of every one of the four component "
                    f"strands.{runner_vuln} This is the basis for recommending that "
                    f"{top_risk.location} be treated as a separate planning case rather "
                    f"than one county among six.",
            caveat="The index is min–max scaled <i>within the counties on screen</i>, so "
                   "0 and 100 mean “least and most vulnerable of this group”, not an "
                   "absolute national score. The four strands are equally weighted — "
                   "a defensible default, and the component matrix beside it lets the "
                   "client re-weight by inspection.",
            table=vuln.round(2).rename(columns={
                "location": "County", "mean_mm": "Mean rainfall (mm)", "cv_pct": "CV (%)",
                "longest_dry_days": "Longest dry spell (days)",
                "dry_day_pct": "Dry days (%)", "mean_temp": "Mean temp (°C)",
                "index": "Index", "tier": "Tier"})[
                ["County", "Index", "Tier", "Mean rainfall (mm)", "CV (%)",
                 "Longest dry spell (days)", "Dry days (%)", "Mean temp (°C)"]])

    with r2:
        strands = {"s_aridity": "Aridity<br>(low rainfall)",
                   "s_variability": "Variability<br>(CV)",
                   "s_persistence": "Persistence<br>(dry spells)",
                   "s_heat": "Heat stress<br>(temperature)"}
        mat = vuln.set_index("location")[list(strands)].reindex(vuln.location)
        raw = vuln.set_index("location")[["mean_mm", "cv_pct", "longest_dry_days",
                                          "mean_temp"]].reindex(vuln.location)
        labels = np.column_stack([
            raw.mean_mm.map(lambda v: f"{v:.0f} mm"),
            raw.cv_pct.map(lambda v: f"{v:.0f}%"),
            raw.longest_dry_days.map(lambda v: f"{v:.0f} d"),
            raw.mean_temp.map(lambda v: f"{v:.1f}°C"),
        ])
        fig = labelled_heatmap(
            mat.values, list(strands.values()), mat.index, labels,
            colorscale=ramp(SEQ_BLUE), zmin=0, zmax=1,
            colorbar_title="scaled<br>severity",
            hovertemplate="%{y} · %{x}<br>scaled severity %{z:.2f} "
                          "(1 = worst on screen)<extra></extra>")
        fig.update_layout(title="What each county's score is made of",
                          xaxis_title=None, yaxis_title=None, height=400,
                          margin=dict(l=90, r=95, t=56, b=70))
        chart_block(
            fig, key="q5_matrix",
            finding="Reading down the columns separates two different problems: some "
                    "counties are dark on <i>aridity and persistence</i> (a water-supply "
                    "problem, fixed with storage and boreholes) while others are dark "
                    "only on <i>variability</i> (a predictability problem, fixed with "
                    "forecasting, insurance and flexible cropping calendars). The "
                    "intervention should match the dark column, not the total.",
            table=mat.round(3).reset_index().rename(columns={"location": "County"}))

    st.markdown("##### Every prolonged dry spell in the record")
    if spells.empty or spells[spells.days >= min_spell].empty:
        st.info(f"No dry spells of {min_spell}+ days at a {dry_threshold:g} mm threshold "
                f"for the current selection.")
    else:
        show = spells[spells.days >= min_spell].copy()
        order = (show.groupby("location").days.max().sort_values(ascending=False).index)
        # Ramp starts one step in from the lightest blue: these bars are thin, and
        # the palette's faintest step would disappear into the surface.
        fig = px.timeline(
            show, x_start="start", x_end="end_excl", y="location", color="days",
            color_continuous_scale=ramp(SEQ_BLUE[1:]),
            category_orders={"location": list(order)[::-1]},
            custom_data=["location", "days", "start", "end"])
        fig.update_traces(
            marker_line_width=0,
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} dry days<br>"
                          "%{customdata[2]|%d %b %Y} → %{customdata[3]|%d %b %Y}"
                          "<extra></extra>")
        fig.update_layout(
            title=f"Dry spells of {min_spell}+ consecutive days below {dry_threshold:g} mm",
            xaxis_title=None, yaxis_title=None, height=330,
            coloraxis_colorbar=dict(title=dict(text="days", side="right"), thickness=12,
                                    len=0.7, outlinewidth=0, tickfont=dict(color=MUTED)),
            margin=dict(l=90, r=30, t=56, b=40))
        fig.update_yaxes(autorange="reversed")
        summary = (show.groupby("location")
                       .agg(spells=("days", "size"), longest=("days", "max"),
                            total_dry_days=("days", "sum"), median=("days", "median"))
                       .reindex(order).reset_index())
        chart_block(
            fig, key="q5_timeline",
            finding=f"<b>{longest.location}</b> holds the longest spell in the record: "
                    f"<b>{int(longest.days)} consecutive days</b> below "
                    f"{dry_threshold:g} mm, from {longest.start:%d %b %Y} to "
                    f"{longest.end:%d %b %Y}. Its row is also the most crowded, "
                    f"with {int(summary.loc[summary.location == longest.location, 'spells'].iloc[0])} "
                    f"spells of {min_spell}+ days over the period — dryness there is the "
                    f"normal state, not an event. This is the single most useful number "
                    f"for sizing water storage: infrastructure must bridge the longest "
                    f"observed gap, not the average one.",
            table=summary.rename(columns={
                "location": "County", "spells": f"Spells ≥{min_spell} days",
                "longest": "Longest (days)", "total_dry_days": "Days in such spells",
                "median": "Median spell (days)"}))

# Tab 6 = Q6 Drill down to one county's raw record
with tabs[6]:
    st.markdown("#### Drill down to one county's raw record")
    st.caption("Clicking a bubble on the executive-summary map also sets this selector. "
               "Everything here is daily-level data — the level at which the aggregates "
               "elsewhere can be audited.")

    default = st.session_state.get("drill_county", ordered[0])
    if default not in ordered:
        default = ordered[0]
    d1, d2 = st.columns([1, 2])
    county = d1.selectbox("County", ordered, index=ordered.index(default), key="drill_pick")
    st.session_state["drill_county"] = county
    focus_years = d2.select_slider(
        "Zoom to years", options=list(range(year_range[0], year_range[1] + 1)),
        value=(year_range[0], year_range[1]), key="drill_years")

    sub = df[(df.location == county) & df.year.between(*focus_years)].sort_values("date")
    cvals = rain_var[rain_var.location == county].iloc[0]
    tr = trends[trends.location == county].iloc[0]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{county} · mean temperature", f"{sub.temperature_2m_mean.mean():.1f} °C",
              f"range {sub.temperature_2m_min.min():.1f}–{sub.temperature_2m_max.max():.1f} °C",
              delta_color="off", delta_arrow="off",
              chart_data=temp_year[temp_year.location == county].mean_temp.tolist(),
              chart_type="line")
    m2.metric("Average annual rainfall", f"{cvals.mean_mm:.0f} mm",
              f"CV {cvals.cv_pct:.1f}% · {cvals.min_mm:.0f}–{cvals.max_mm:.0f} mm",
              delta_color="off", delta_arrow="off",
              chart_data=rain_year[rain_year.location == county].rain.tolist(),
              chart_type="bar")
    m3.metric("Wettest day on record", f"{sub.precipitation_sum.max():.0f} mm",
              f"{sub.loc[sub.precipitation_sum.idxmax(), 'date']:%d %b %Y}",
              delta_color="off", delta_arrow="off")
    m4.metric("Trend", f"{tr.per_decade:+.2f} °C/decade",
              f"p = {tr.p_value:.3f} · {'significant' if tr.significant else 'not significant'}",
              delta_color="off", delta_arrow="off")

    # Two stacked charts sharing one x-axis instead of one dual-axis chart:
    # temperature and rainfall have different units, and overlaying them on two
    # y-scales would let the reader invent a relationship by rescaling.
    roll = max(int(smooth_days), 1)
    temp_s = sub.set_index("date").temperature_2m_mean.rolling(roll, min_periods=1).mean()
    fig = go.Figure()
    if roll > 1:
        fig.add_trace(go.Scatter(
            x=sub.date, y=sub.temperature_2m_mean, mode="lines", name="Daily",
            line=dict(color=GRID, width=1), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=temp_s.index, y=temp_s.values, mode="lines",
        name=f"{roll}-day mean" if roll > 1 else "Daily mean",
        line=dict(color=COUNTY_COLOR[county], width=2),
        hovertemplate="%{x|%d %b %Y}<br>%{y:.1f} °C<extra></extra>"))
    fig.update_layout(title=f"{county} · daily mean temperature", yaxis_title="°C",
                      xaxis_title=None, height=290, margin=dict(l=70, r=30, t=50, b=20))
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="dd_temp")

    monthly = (sub.groupby(sub.date.dt.to_period("M").dt.to_timestamp(), as_index=False)
                  .precipitation_sum.sum().rename(columns={"date": "month_start"}))
    monthly.columns = ["month_start", "rain"]
    normal = monthly.rain.mean()
    fig = go.Figure(go.Bar(
        x=monthly.month_start, y=monthly.rain,
        marker=dict(color=np.where(monthly.rain >= normal, SEQ_BLUE[4], "#e34948"),
                    line=dict(width=0)),
        hovertemplate="%{x|%b %Y}<br>%{y:.0f} mm<extra></extra>"))
    fig.add_hline(y=normal, line=dict(color=INK_2, width=1, dash="dash"),
                  annotation_text=f" monthly average {normal:.0f} mm ",
                  annotation_position="top left",
                  annotation_font=dict(color=INK_2, size=11),
                  annotation_bgcolor=SURFACE)
    fig.update_layout(title=f"{county} · monthly rainfall against its own average",
                      yaxis_title="mm", xaxis_title=None, height=290,
                      margin=dict(l=70, r=30, t=50, b=40))
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="dd_rain")
    # The pair shares one date axis rather than one frame with two y-scales: two
    # measures in different units on a single pair of axes invites a correlation
    # that is not there.
    st.caption(f"Blue months are wetter than {county}'s own monthly average, red drier.")

    with st.expander(f"Variable relationships in {county} (correlation matrix)"):
        corr = sub[DAILY_VARIABLES].corr()
        fig = labelled_heatmap(
            corr.values, [PRETTY[c] for c in corr.columns],
            [PRETTY[c] for c in corr.index],
            [[f"{v:+.2f}" for v in row] for row in corr.values],
            colorscale=DIV_RAIN, zmid=0, zmin=-1, zmax=1, colorbar_title="r",
            hovertemplate="%{y}<br>vs %{x}<br>r = %{z:+.2f}<extra></extra>")
        fig.update_layout(title=f"Pearson correlation, daily values · {county}",
                          height=460, margin=dict(l=180, r=80, t=56, b=150))
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="dd_corr")
        st.caption("Diverging scale because correlation has a meaningful zero: red is "
                   "negative, blue positive, grey none. The rainfall–temperature cell is "
                   "the one to read — where it is clearly negative, wet months are cool "
                   "months, meaning cloud cover and rainfall move together with "
                   "temperature suppression.")

    with st.expander(f"Daily records for {county} ({len(sub):,} rows)"):
        st.dataframe(sub[["date", "location"] + DAILY_VARIABLES]
                     .rename(columns={"date": "Date", "location": "County", **PRETTY}),
                     width="stretch", hide_index=True, height=360)
        st.download_button(f"Download {county} daily data (CSV)",
                           sub.to_csv(index=False).encode(),
                           file_name=f"{county.lower()}_daily.csv", key="dl_deep")

# Tab 7 = Q7 Data provenance, quality and cleaning
with tabs[7]:
    st.markdown("#### 1 · Where the data comes from")
    a1, a2 = st.columns([1, 1], gap="large")
    with a1:
        st.markdown(f"""
- **API** — Open-Meteo Historical Weather (ERA5 reanalysis) Archive
- **Endpoint** — `{BASE_URL}`
- **Method** — one `GET` per station, six calls in total

**Request parameters**

| Parameter | Value |
|---|---|
| `latitude`, `longitude` | one call per station (six calls) |
| `start_date` | `{START_DATE}` |
| `end_date` | `{END_DATE}` |
| `daily` | the six variables listed opposite |
| `timezone` | `Africa/Nairobi` |

Requests retry with escalating back-off on HTTP 429, and each response is written
to `data/raw/<county>.json` before any processing, so the raw evidence is
reproducible and the pipeline can resume without re-fetching.
        """)
    with a2:
        st.markdown("**Variables retrieved**")
        st.dataframe(pd.DataFrame({
            "API variable": DAILY_VARIABLES,
            "Meaning": [PRETTY[v] for v in DAILY_VARIABLES],
            "Plausible range used": [f"{lo} – {hi}" for lo, hi in
                                     (PLAUSIBLE_RANGES[v] for v in DAILY_VARIABLES)],
        }), width="stretch", hide_index=True)
        st.markdown(f"**Stations** {len(LOCATIONS)} · **Days requested** "
                    f"{quality['expected_days']:,} per station · "
                    f"**Rows retrieved** {quality['rows_raw']:,}")

    st.markdown("#### 2 · Data quality assessment")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Completeness", f"{min(quality['completeness'].values()):.1f}%",
              "of expected days present", delta_color="off", delta_arrow="off")
    q2.metric("Duplicate records", f"{quality['duplicates']:,}",
              "same county + date", delta_color="off", delta_arrow="off")
    q3.metric("Missing values", f"{sum(quality['nans'].values()):,}",
              "NaNs in retrieved rows", delta_color="off", delta_arrow="off")
    q4.metric("Implausible values", f"{sum(quality['outliers'].values()):,}",
              "outside physical bounds", delta_color="off", delta_arrow="off")

    st.dataframe(pd.DataFrame({
        "County": list(LOCATIONS),
        "Days present": [int(quality["completeness"][l] * quality["expected_days"] / 100)
                         for l in LOCATIONS],
        "Missing days": [quality["missing_dates"][l] for l in LOCATIONS],
        "Completeness (%)": [round(quality["completeness"][l], 2) for l in LOCATIONS],
    }), width="stretch", hide_index=True)

    st.markdown(f"""
<div class="finding">The archive returned a complete,
gap-free record: {quality['rows_raw']:,} rows, {quality['duplicates']} duplicates,
{sum(quality['nans'].values())} missing values and
{sum(quality['outliers'].values())} physically implausible values. That is expected
for a reanalysis product, which is modelled onto a regular grid rather than read off
instruments — and it is worth stating plainly in the presentation, because
<i>"we found no problems"</i> is only credible if you can show the tests you ran.
The cleaning steps below therefore act as guarantees rather than repairs, and they
still matter: they are what make the claim verifiable.</div>
    """, unsafe_allow_html=True)

    st.markdown("#### 3 · Cleaning and preparation decisions")
    st.dataframe(pd.DataFrame([
        ("Duplicate location–date rows", "Dropped, keeping the first occurrence",
         "A repeated day would be double-counted in every annual total."),
        ("Values outside physical bounds", "Set to missing, row retained",
         "The other five variables recorded that day are still usable."),
        ("Whole days absent", "Reindexed against the full daily calendar",
         "Makes a gap an explicit row instead of a silent absence."),
        (f"Gaps of ≤{MAX_GAP_DAYS} days", "Linear interpolation",
         "Weather is autocorrelated over a few days; longer gaps are not guessed."),
        (f"Gaps of >{MAX_GAP_DAYS} days", "Left missing",
         "Interpolating a long gap would invent data and flatter variability."),
        ("Units and schema", "Verified consistent (°C, mm, km/h); column order standardised",
         "All six stations come from one API contract, so no conversion was required."),
    ], columns=["Issue", "Decision", "Why"]), width="stretch", hide_index=True)

    st.markdown("#### 4 · Statistical techniques used")
    st.dataframe(pd.DataFrame([
        ("Descriptive statistics & coefficient of variation",
         "Q1, Q2", "CV standardises spread by the mean, making counties with very "
         "different rainfall totals comparable."),
        ("Ordinary least squares trend + t-test on the slope, with 95% CI",
         "Q3", "Tests whether a decade of annual means supports a warming claim; the "
         "interval communicates the uncertainty a bare slope hides."),
        ("Standardised anomalies (z-scores against each county's own mean)",
         "Q2, Q5", "Puts wet and dry counties on one scale so drought years can be "
         "compared across the country."),
        ("Run-length analysis of consecutive dry days",
         "Q5", "Turns a daily series into the planning-relevant number: the longest "
         "unbroken period with no usable rain."),
        ("Min–max normalised composite index over four strands",
         "Q5", "Combines aridity, variability, persistence and heat into one ranking "
         "while keeping each component inspectable."),
        ("Pearson correlation matrix of the daily variables",
         "Deep dive", "Quantifies the rainfall–temperature coupling that explains why "
         "wet months are cool months."),
    ], columns=["Technique", "Used for", "Why this one"]), width="stretch", hide_index=True)

    st.markdown("#### 5 · Evidence-linked recommendations for the client")
    st.markdown(f"""
Each recommendation below names the chart it rests on, so it can be defended in the
oral presentation without leaving the dashboard.

| # | Recommendation to county governments | Evidence in this dashboard |
|---|---|---|
| 1 | Treat **{top_risk.location}** as a standing water-scarcity emergency, not a seasonal one: size storage and borehole capacity to bridge a **{int(top_risk.longest_dry_days)}-day** no-rain window, and pre-position livestock water points before the Jan–Feb and Jun–Sep dry windows. | Q5 index **{top_risk['index']:.0f}/100**; lowest rainfall **{top_risk.mean_mm:.0f} mm**; longest dry spell **{int(top_risk.longest_dry_days)} days**; dry-spell timeline shows dryness is its normal state. |
| 2 | Fund **rainwater harvesting and multi-year storage** where rainfall is erratic rather than merely low — **{most_variable.location}** first (**CV {most_variable.cv_pct:.1f}%**, {most_variable.min_mm:.0f}–{most_variable.max_mm:.0f} mm). Systems sized to the mean will fail in the dry tail. | Q2 quadrant chart and the ten-year box distribution. |
| 3 | Put **flood and drainage readiness on the calendar**: crews, desilting and early warning in place before **{wettest_month.month_name}**, and again before the October–December short rains. | Q4 climatology heatmap: two dark bands, **{wettest_month.month_name}** wettest nationally at **{wettest_month.mm_per_month:.0f} mm**. |
| 4 | **Do not build a national rainfall calendar.** Counties whose peak is in the short rains need a different readiness schedule from the April-peak counties. | Q4 per-county peaks differ; the caveat box on that tab lists them. |
| 5 | **Report temperature as an interval, not a trend, and re-test on a 30-year window.** No county shows significant warming here, so a warming claim from this record would not survive scrutiny — while the absence of one is not evidence of stability either. | Q3 confidence-interval plot: all {len(trends)} intervals cross zero. |
| 6 | Match the intervention to the **dark column, not the total**: aridity and persistence call for storage; variability alone calls for forecasting, index insurance and flexible planting calendars. | Q5 component matrix separates the two failure modes. |
    """)

    st.markdown("#### 6 · Reproducibility")
    st.markdown(f"""
- **Cleaned dataset** `{CLEAN_CSV}` — {quality['rows_clean']:,} rows, written by this app
  on first run if the notebook has not already produced it.
- **Raw responses** `data/raw/*.json` — one file per county, exactly as returned.
- **This dashboard** `dashboard.py` — recomputes every figure from the cleaned data at
  load time. No number on any tab is hard-coded, which is why the narrative text
  updates when you change a filter.
    """)
    full = data.drop(columns=["month_name", "doy"])
    st.download_button("Download the full cleaned dataset (CSV)",
                       full.to_csv(index=False).encode(),
                       file_name="kenya_weather_cleaned.csv", key="dl_full")

st.markdown(f"""
<hr style="border:none;border-top:1px solid {GRID};margin:2rem 0 0.8rem 0">
<div style="color:{MUTED};font-size:0.82rem">
MIT 8334 Data Analytics and Visualization · Capstone Project, Group 3
</div>
""", unsafe_allow_html=True)
