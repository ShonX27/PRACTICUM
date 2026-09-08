import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(
    page_title="OBA Donations Dashboard",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path("data")

# ---------------------------------------------------------------------------
# Fixed color identity — a channel always keeps the same color no matter what
# is filtered in or out. Order follows the validated categorical palette.
# ---------------------------------------------------------------------------
CHANNEL_ORDER = ["DonorBox", "GoFundMe", "E-transfer to our bank", "PayPal", "Unknown"]
CHANNEL_COLORS = {
    "DonorBox": "#2a78d6",              # blue
    "GoFundMe": "#1baf7a",              # aqua
    "E-transfer to our bank": "#eb6834",  # orange
    "PayPal": "#eda100",                # yellow
    "Unknown": "#898781",               # muted — not a real identity
}
FALLBACK_COLORS = ["#4a3aa7", "#e87ba4", "#e34948", "#008300"]

STATUS_COLORS = {"Active": "#0ca30c", "Inactive": "#898781"}

CHART_FONT = dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color="#c3c2b7")
SURFACE = "#161615"
GRID = "#2c2c2a"


def channel_color(name: str, seen: dict) -> str:
    if name in CHANNEL_COLORS:
        return CHANNEL_COLORS[name]
    if name not in seen:
        seen[name] = FALLBACK_COLORS[len(seen) % len(FALLBACK_COLORS)]
    return seen[name]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    oba_clean = pd.read_csv(DATA_DIR / "ob_donations.csv")
    brooks_clean = pd.read_csv(DATA_DIR / "bfi.csv")
    order_clean_final = pd.read_csv(DATA_DIR / "order_data_multilevel.csv")
    pali_clean = pd.read_csv(DATA_DIR / "donors_palinight.csv")

    donations_master = pd.concat(
        [
            oba_clean[["date", "amount", "channel", "source_file"]],
            brooks_clean.assign(date=pd.NaT)[["date", "amount", "channel", "source_file"]],
            pali_clean[["date", "amount", "channel", "source_file"]],
        ],
        ignore_index=True,
    )
    donations_master["date"] = pd.to_datetime(donations_master["date"], errors="coerce")
    return donations_master, order_clean_final


donations_master, order_clean_final = load_data()

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Make the KPI buttons bigger and left-aligned — targets Streamlit's own
       stable button testid, not guessed internal class names, so this keeps
       working regardless of theme or Streamlit version. */
    div[data-testid="stButton"] button {
        min-height: 74px;
        height: auto !important;
        text-align: left;
        justify-content: flex-start;
        align-items: center;
        border-radius: 12px;
        padding: 10px 14px;
    }
    div[data-testid="stButton"] button p,
    div[data-testid="stButton"] button * {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        text-align: left;
        font-size: 14px;
        line-height: 1.35;
        margin: 0;
    }
    .dash-title { font-size: 34px; font-weight: 800; margin-bottom: 0px; }
    .dash-sub { margin-top: -6px; margin-bottom: 18px; opacity: 0.75; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _set_view(view_key):
    st.session_state.active_view = view_key


def kpi_button(col, key, icon, label, value, sub, sub_class, is_active):
    # on_click fires (and updates session_state) BEFORE this script body
    # re-runs, so the highlight below reflects the click on the same pass —
    # no one-click lag.
    with col:
        st.button(
            f"{icon} {label}: **{value}**",
            key=f"btn_{key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            on_click=_set_view,
            args=(key,),
        )
        if sub:
            st.caption(sub)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<div class="dash-title">💠 OBA Donations & Fundraising</div>', unsafe_allow_html=True)
st.markdown('<div class="dash-sub">Inbound donations across all channels — de-identified, aggregate view</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

channels = sorted(donations_master["channel"].dropna().unique())
selected_channels = st.sidebar.multiselect("Channel", channels, default=channels)

valid_dates = donations_master["date"].dropna()
if not valid_dates.empty:
    min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
    date_range = st.sidebar.date_input("Date range (undated records always included)", (min_d, max_d))
else:
    date_range = None

st.sidebar.caption("Records with no date (e.g. individual fundraiser totals) are always included in totals but excluded from time-based charts.")

filtered = donations_master[donations_master["channel"].isin(selected_channels)].copy()
if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    has_date = filtered["date"].notna()
    in_range = filtered["date"].between(start, end)
    filtered = filtered[~has_date | in_range]

# ---------------------------------------------------------------------------
# Shared aggregates
# ---------------------------------------------------------------------------
dated = filtered.dropna(subset=["date"]).copy()
if not dated.empty:
    dated["month"] = dated["date"].dt.to_period("M").dt.to_timestamp()
    monthly = dated.groupby("month").agg(amount=("amount", "sum"), n=("amount", "count")).reset_index()
else:
    monthly = pd.DataFrame(columns=["month", "amount", "n"])

by_channel_all = filtered.groupby("channel")["amount"].sum().sort_values(ascending=False)
sorted_amounts = filtered["amount"].dropna().sort_values(ascending=False).reset_index(drop=True)

total = filtered["amount"].sum()
count = len(filtered)
avg = total / count if count else 0

if len(sorted_amounts) > 0:
    top10_n = max(1, int(len(sorted_amounts) * 0.10))
    top10_share = sorted_amounts.head(top10_n).sum() / sorted_amounts.sum() * 100
else:
    top10_share = 0

active_n = int((order_clean_final["status"] == "Active").sum())
total_fundraisers = len(order_clean_final)

if len(monthly) >= 2:
    last_amt, prev_amt = monthly["amount"].iloc[-1], monthly["amount"].iloc[-2]
    mom_pct = ((last_amt - prev_amt) / prev_amt * 100) if prev_amt else None
else:
    mom_pct = None

if mom_pct is None:
    total_sub, total_sub_class = "", ""
else:
    arrow = "▲" if mom_pct >= 0 else "▼"
    total_sub_class = "up" if mom_pct >= 0 else "down"
    total_sub = f"{arrow} {abs(mom_pct):.1f}% vs prior month"

if len(by_channel_all) > 0:
    top_channel_name = by_channel_all.index[0]
else:
    top_channel_name = "n/a"

# ---------------------------------------------------------------------------
# KPI row — each card is a clickable button that switches the section below
# ---------------------------------------------------------------------------
if "active_view" not in st.session_state:
    st.session_state.active_view = "total"

c1, c2, c3, c4, c5 = st.columns(5)
kpi_button(c1, "total", "💰", "Total Raised (CAD)", f"${total:,.0f}", total_sub, total_sub_class,
           st.session_state.active_view == "total")
kpi_button(c2, "avg", "🧾", "Avg. Donation", f"${avg:,.0f}", "", "",
           st.session_state.active_view == "avg")
kpi_button(c3, "top10", "🔥", "Top 10% Share", f"{top10_share:.1f}%", "", "",
           st.session_state.active_view == "top10")
kpi_button(c4, "fund", "🎯", "Active Fundraisers", f"{active_n}/{total_fundraisers}", "", "",
           st.session_state.active_view == "fund")
kpi_button(c5, "channel", "🏆", "Top Channel", top_channel_name, "", "",
           st.session_state.active_view == "channel")

st.write("")
view = st.session_state.active_view

# ---------------------------------------------------------------------------
# Total Raised → Trend
# ---------------------------------------------------------------------------
if view == "total":
    st.markdown("#### 📈 Total Raised Over Time")
    if not dated.empty:
        trend_mode = st.radio("View", ["Total raised", "By channel"], horizontal=True, label_visibility="collapsed")

        if trend_mode == "Total raised":
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=monthly["month"], y=monthly["amount"],
                mode="lines+markers",
                line=dict(color="#2a78d6", width=2, shape="spline"),
                marker=dict(size=9, color="#2a78d6", line=dict(width=2, color=SURFACE)),
                fill="tozeroy", fillcolor="rgba(42,120,214,0.12)",
                hovertemplate="<b>%{x|%b %Y}</b><br>Raised: $%{y:,.0f}<br>Records: %{customdata}<extra></extra>",
                customdata=monthly["n"],
                name="Total raised",
            ))
            fig.update_layout(
                height=430, margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)",
                font=CHART_FONT, hovermode="x unified", showlegend=False,
                xaxis=dict(showgrid=False, rangeslider=dict(visible=True, bgcolor=SURFACE, thickness=0.08),
                           linecolor=GRID),
                yaxis=dict(title="Amount (CAD)", gridcolor=GRID, zeroline=False, tickprefix="$"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            pivot = dated.pivot_table(index="month", columns="channel", values="amount", aggfunc="sum", fill_value=0)
            ordered_cols = [c for c in CHANNEL_ORDER if c in pivot.columns] + \
                           [c for c in pivot.columns if c not in CHANNEL_ORDER]
            seen = {}
            fig = go.Figure()
            for c in ordered_cols:
                fig.add_trace(go.Scatter(
                    x=pivot.index, y=pivot[c], name=c, mode="lines",
                    stackgroup="one", line=dict(width=0.5, color=channel_color(c, seen)),
                    fillcolor=channel_color(c, seen),
                    hovertemplate=f"<b>{c}</b><br>" + "%{x|%b %Y}: $%{y:,.0f}<extra></extra>",
                ))
            fig.update_layout(
                height=430, margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)",
                font=CHART_FONT, hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"),
                xaxis=dict(showgrid=False, linecolor=GRID),
                yaxis=dict(title="Amount (CAD)", gridcolor=GRID, zeroline=False, tickprefix="$"),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No dated records for the selected filters.")

# ---------------------------------------------------------------------------
# Avg. Donation → distribution of individual donation amounts + raw data
# ---------------------------------------------------------------------------
elif view == "avg":
    st.markdown("#### 🧾 Donation Size Distribution")
    amt = filtered["amount"].dropna()
    if len(amt):
        fig = go.Figure(go.Histogram(
            x=amt, nbinsx=30, marker=dict(color="#2a78d6", line=dict(color=SURFACE, width=1)),
            hovertemplate="Amount: $%{x:,.0f}<br>Count: %{y}<extra></extra>",
        ))
        fig.add_vline(x=amt.mean(), line=dict(color="#eb6834", width=2, dash="dash"))
        fig.update_layout(
            height=400, margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
            xaxis=dict(title="Donation amount (CAD)", gridcolor=GRID, tickprefix="$"),
            yaxis=dict(title="Number of records", gridcolor=GRID), bargap=0.05,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Dashed line = average donation (\\${amt.mean():,.0f}). Median is \\${amt.median():,.0f}.")
    else:
        st.info("No donation amounts available for the selected filters.")

    with st.expander("View & download raw records"):
        st.dataframe(filtered.sort_values("date", na_position="last"), use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ Download filtered data as CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="filtered_donations.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------------------------
# Top 10% Share → Concentration deep dive
# ---------------------------------------------------------------------------
elif view == "top10":
    st.markdown("#### 🔥 Donation Concentration")
    st.caption("Explore how concentrated giving is — how much of the total comes from a small share of donations.")

    pct = st.select_slider("Look at the top ___% of donations", options=[5, 10, 15, 20, 25, 30, 40, 50], value=10)

    n = len(sorted_amounts)
    if n > 0:
        top_n = max(1, int(n * pct / 100))
        top_share = sorted_amounts.head(top_n).sum() / sorted_amounts.sum() * 100

        st.info(
            f"💡 The top **{pct}%** of donations "
            f"(**{top_n}** of {n} records) account for **{top_share:.1f}%** of all funds raised."
        )

        cum_pct_records = np.arange(1, n + 1) / n * 100
        cum_pct_amount = sorted_amounts.cumsum() / sorted_amounts.sum() * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[0, 100], y=[0, 100], mode="lines", line=dict(color="#3a3a37", width=2, dash="dot"),
            name="Perfectly even giving", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=cum_pct_records, y=cum_pct_amount, mode="lines",
            line=dict(color="#eb6834", width=2), fill="tonexty", fillcolor="rgba(235,104,52,0.10)",
            name="Actual giving",
            hovertemplate="Top %{x:.0f}% of donations<br>= %{y:.1f}% of funds<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[pct], y=[top_share], mode="markers", marker=dict(size=11, color="#eb6834", line=dict(width=2, color=SURFACE)),
            showlegend=False, hovertemplate=f"Top {pct}% = {top_share:.1f}% of funds<extra></extra>",
        ))
        fig.update_layout(
            height=420, margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left"),
            xaxis=dict(title="Cumulative % of donations (largest first)", gridcolor=GRID, ticksuffix="%", range=[0, 100]),
            yaxis=dict(title="Cumulative % of funds raised", gridcolor=GRID, ticksuffix="%", range=[0, 100]),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("The further the orange line bows away from the dotted diagonal, the more concentrated giving is among a few large donations.")

        with st.expander(f"Ranked view of the top {min(top_n, 25)} donations (de-identified)"):
            top_table = filtered.dropna(subset=["amount"]).sort_values("amount", ascending=False).head(min(top_n, 25))
            top_table = top_table.assign(rank=range(1, len(top_table) + 1))[["rank", "amount", "channel", "source_file"]]
            st.dataframe(top_table, hide_index=True, use_container_width=True)
    else:
        st.info("No donation amounts available for the selected filters.")

# ---------------------------------------------------------------------------
# Active Fundraisers → status + completion
# ---------------------------------------------------------------------------
elif view == "fund":
    st.markdown("#### 🎯 Fundraiser Status & Completion")
    left, right = st.columns(2)
    with left:
        status_counts = order_clean_final["status"].value_counts()
        fig3 = go.Figure(go.Pie(
            labels=status_counts.index, values=status_counts.values, hole=0.55,
            marker=dict(colors=[STATUS_COLORS.get(s, "#898781") for s in status_counts.index],
                        line=dict(color=SURFACE, width=2)),
            textinfo="label+percent", textfont=dict(color="#ffffff", size=13),
            hovertemplate="<b>%{label}</b>: %{value} (%{percent})<extra></extra>",
        ))
        fig3.update_layout(
            height=360, margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT, showlegend=False,
            title=dict(text="Fundraiser Status", font=dict(size=14, color="#c3c2b7")),
        )
        st.plotly_chart(fig3, use_container_width=True)

    with right:
        comp = order_clean_final["completion_pct"].dropna()
        fig4 = go.Figure(go.Histogram(
            x=comp, nbinsx=20, marker=dict(color="#2a78d6",
                                            line=dict(color=SURFACE, width=1)),
            hovertemplate="Completion: %{x:.0f}%<br>Fundraisers: %{y}<extra></extra>",
        ))
        if len(comp):
            fig4.add_vline(x=comp.mean(), line=dict(color="#eb6834", width=2, dash="dash"))
        fig4.update_layout(
            height=360, margin=dict(l=10, r=10, t=30, b=10),
            plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
            title=dict(text="Completion % Distribution (dashed = average)", font=dict(size=14, color="#c3c2b7")),
            xaxis=dict(title="Completion %", gridcolor=GRID, ticksuffix="%"),
            yaxis=dict(title="Fundraisers", gridcolor=GRID), bargap=0.05,
        )
        st.plotly_chart(fig4, use_container_width=True)

# ---------------------------------------------------------------------------
# Top Channel → channel breakdown + momentum
# ---------------------------------------------------------------------------
elif view == "channel":
    st.markdown("#### 🏆 Channel Breakdown")
    by_channel = by_channel_all
    seen = {}
    colors = [channel_color(c, seen) for c in by_channel.index]

    left, right = st.columns([1.1, 1])
    with left:
        fig = go.Figure(go.Pie(
            labels=by_channel.index, values=by_channel.values,
            hole=0.55, marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
            textinfo="percent", textfont=dict(color="#ffffff", size=13),
            hovertemplate="<b>%{label}</b><br>$%{value:,.0f} (%{percent})<extra></extra>",
        ))
        fig.update_layout(
            height=380, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, x=0.5, xanchor="center"),
            annotations=[dict(text=f"${by_channel.sum():,.0f}", x=0.5, y=0.5, showarrow=False,
                               font=dict(size=20, color="#ffffff"))],
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig2 = go.Figure(go.Bar(
            x=by_channel.values, y=by_channel.index, orientation="h",
            marker=dict(color=colors),
            hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>",
        ))
        fig2.update_layout(
            height=380, margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
            xaxis=dict(gridcolor=GRID, tickprefix="$"), yaxis=dict(autorange="reversed"),
            bargap=0.35,
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("##### Momentum — this month vs. last month, by channel")
    if len(monthly) >= 2 and not dated.empty:
        pivot = dated.pivot_table(index="month", columns="channel", values="amount", aggfunc="sum", fill_value=0)
        last_m, prev_m = pivot.index[-1], pivot.index[-2]
        mom_cols = st.columns(len(pivot.columns)) if len(pivot.columns) else [st]
        for col, ch in zip(mom_cols, pivot.columns):
            last_v, prev_v = pivot.loc[last_m, ch], pivot.loc[prev_m, ch]
            delta_pct = ((last_v - prev_v) / prev_v * 100) if prev_v else None
            if delta_pct is None:
                col.metric(ch, f"${last_v:,.0f}")
            else:
                col.metric(ch, f"${last_v:,.0f}", f"{delta_pct:+.0f}%")
    else:
        st.caption("Need at least two months of dated records in the current filter to show momentum.")

    with st.expander("Channel share as a table (accessible view)"):
        share = (filtered["channel"].value_counts(normalize=True) * 100).round(1)
        st.dataframe(
            pd.DataFrame({"channel": share.index, "raised": by_channel.reindex(share.index).values,
                          "% of records": share.values}),
            hide_index=True, use_container_width=True,
        )
