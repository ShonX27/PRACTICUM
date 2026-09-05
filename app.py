import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

st.set_page_config(page_title="OBA Donations Dashboard", layout="wide")

DATA_DIR = Path("data")


@st.cache_data
def load_data():
    oba_clean = pd.read_csv(DATA_DIR / "ob_donations.csv")
    brooks_clean = pd.read_csv(DATA_DIR / "bfi.csv")
    order_clean_final = pd.read_csv(DATA_DIR / "order_data_multilevel.csv")
    pali_clean = pd.read_csv(DATA_DIR / "donors_palinight.csv")

    # Same merge as Cell 9 in the notebook
    donations_master = pd.concat(
        [
            oba_clean[["date", "amount", "channel", "source_file"]],
            brooks_clean.assign(date=pd.NaT)[["date", "amount", "channel", "source_file"]],
            pali_clean[["date", "amount", "channel", "source_file"]],
        ],
        ignore_index=True,
    )

    return donations_master, order_clean_final


donations_master, order_clean_final = load_data()

st.title("OBA Donations & Fundraising Dashboard")

# --- Sidebar filters ---
st.sidebar.header("Filters")
channels = sorted(donations_master["channel"].dropna().unique())
selected_channels = st.sidebar.multiselect("Channel", channels, default=channels)

filtered = donations_master[donations_master["channel"].isin(selected_channels)]

# --- Top metrics ---
col1, col2, col3 = st.columns(3)
col1.metric("Total Raised (CAD)", f"${filtered['amount'].sum():,.2f}")
col2.metric("Number of Records", f"{len(filtered):,}")

sorted_amounts = filtered["amount"].dropna().sort_values(ascending=False)
if len(sorted_amounts) > 0:
    top_n = max(1, int(len(sorted_amounts) * 0.10))
    top_share = sorted_amounts.head(top_n).sum() / sorted_amounts.sum() * 100
    col3.metric("Top 10% Donor Share", f"{top_share:.1f}%")
else:
    col3.metric("Top 10% Donor Share", "n/a")

st.divider()

# --- Chart 1: Total raised over time (monthly) ---
st.subheader("Total Raised Over Time (Monthly)")
dated = filtered.dropna(subset=["date"]).copy()
if not dated.empty:
    dated["month"] = pd.to_datetime(dated["date"]).dt.to_period("M").astype(str)
    monthly = dated.groupby("month")["amount"].sum().reset_index()

    fig1, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(monthly["month"], monthly["amount"], marker="o", color="#FF7F00")
    ax1.set_ylabel("Amount (CAD)")
    ax1.set_title("Total Raised Over Time (Monthly)")
    plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")
    fig1.tight_layout()
    st.pyplot(fig1)
else:
    st.info("No dated records for the selected filters.")

# --- Chart 2: Raised by channel ---
st.subheader("Total Raised by Channel")
by_channel = filtered.groupby("channel")["amount"].sum().sort_values(ascending=False)

fig2, ax2 = plt.subplots(figsize=(6, 4))
by_channel.plot(kind="bar", color="#FF7F00", ax=ax2)
ax2.set_ylabel("Amount (CAD)")
ax2.set_title("Total Raised by Channel")
fig2.tight_layout()
st.pyplot(fig2)

with st.expander("Channel share (% of records)"):
    channel_pct = (filtered["channel"].value_counts(normalize=True) * 100).round(1)
    st.dataframe(channel_pct.rename("percent"))

# --- Chart 3: Fundraiser status + completion % ---
st.subheader("Fundraiser Status & Completion")
fig3, axes = plt.subplots(1, 2, figsize=(10, 4))
order_clean_final["status"].value_counts().plot(kind="bar", ax=axes[0], color="#FF7F00")
axes[0].set_title("Fundraiser Status: Active vs Inactive")
axes[1].hist(order_clean_final["completion_pct"].dropna(), bins=20, color="#FF7F00")
axes[1].set_title("Completion % Distribution")
axes[1].set_xlabel("Completion %")
fig3.tight_layout()
st.pyplot(fig3)

st.divider()
with st.expander("View cleaned donations table"):
    st.dataframe(filtered)
