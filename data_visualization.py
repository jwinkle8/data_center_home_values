import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import textwrap

from event_of_interest import EventOfInterest
from pathlib import Path


EVENT_OF_INTEREST = EventOfInterest.FIRST_OPERATIONAL

data_dir = Path("data")

clean_data_prefix = "operational_" if EVENT_OF_INTEREST == EventOfInterest.FIRST_OPERATIONAL else "headline_"
treated_panel = pd.read_csv(data_dir / "final"  / (clean_data_prefix + "treated_zipcode_value_estimates.csv"))
control_panel = pd.read_csv(data_dir / "final"  / (clean_data_prefix + "control_zipcode_value_estimates.csv"))

# Join each treated zip's own path to its synthetic control path and take the difference.
# Gap is the treated zip's log appreciation since the anchor, net of what its matched donors
# did over the same months; exp(Gap) - 1 is the same thing in percent.
gap_panel = (
    treated_panel[["ZipCode", "EventTime", "RelLogValue"]]
    .rename(columns={"ZipCode": "TreatedZip", "RelLogValue": "Treated"})
    .merge(control_panel.rename(columns={"RelLogValue": "Control"}), on=["TreatedZip", "EventTime"])
)
gap_panel["Gap"] = gap_panel["Treated"] - gap_panel["Control"]

# Nothing should be lost in the join, and the gap is 0 at the anchor by construction.
assert len(gap_panel) == len(treated_panel), "treated and control panels do not line up"
assert np.allclose(gap_panel.loc[gap_panel["EventTime"] == 0, "Gap"], 0)
assert gap_panel["Gap"].notna().all()

print(gap_panel.head(10).to_string(index=False))

N_BOOTSTRAP = 500
RANDOM_SEED = 510

# Point estimate at each event time: the mean gap across treated zips observed there, with
# the mean treated and control paths for plotting and the count behind each point.
event_study = gap_panel.groupby("EventTime").agg(
    Treated=("Treated", "mean"), Control=("Control", "mean"), Gap=("Gap", "mean"), N=("TreatedZip", "size")
)

# Bootstrap the interval by resampling treated zips, not rows. Months within a zip are
# serially correlated, so the zip is the unit of independent variation. Each draw takes a
# whole zip's path along with it; unobserved months are NaN and drop out of the mean.
rng = np.random.default_rng(RANDOM_SEED)
gap_by_zip = gap_panel.pivot(index="TreatedZip", columns="EventTime", values="Gap")
bootstrap_means = np.empty((N_BOOTSTRAP, gap_by_zip.shape[1]))
for draw in range(N_BOOTSTRAP):
    sample = rng.integers(0, len(gap_by_zip), size=len(gap_by_zip))
    bootstrap_means[draw] = np.nanmean(gap_by_zip.to_numpy()[sample], axis=0)
event_study["GapLower"] = np.nanpercentile(bootstrap_means, 2.5, axis=0)
event_study["GapUpper"] = np.nanpercentile(bootstrap_means, 97.5, axis=0)

print(event_study.loc[[-24, -12, 0, 6, 12, 24]].round(4).to_string())

def log_to_pct(log_change):
    return 100 * (np.exp(log_change) - 1)

TREATED_COLOR, CONTROL_COLOR = "#2a78d6", "#eb6834"
INK, MUTED, GRID, BASELINE = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"

plt.rcParams.update({'font.size': 14})
fig, (path_axis, gap_axis) = plt.subplots(
    2, 1, figsize=(10, 8), sharex=True, gridspec_kw={"height_ratios": [3, 2], "hspace": 0.12}
)
event_time = event_study.index

EVENT_WINDOW_MONTHS = 24

# Top: the average treated zip's path against its matched controls, both indexed to 0 at
# the anchor month.
path_axis.plot(event_time, log_to_pct(event_study["Treated"]), color=TREATED_COLOR, linewidth=2, label="Data center zip codes")
path_axis.plot(event_time, log_to_pct(event_study["Control"]), color=CONTROL_COLOR, linewidth=2, label="Comparable zip codes")

event_string = 'data center opened' if EVENT_OF_INTEREST == EventOfInterest.FIRST_OPERATIONAL else 'first data center construction headline'
path_axis.set_ylabel(textwrap.fill(f"Home value change since {event_string} (%)", width=25), color=INK, fontweight='bold', fontsize=15)
path_axis.legend(frameon=False, loc="upper left")
# path_axis.set_title(
#     f"Home values around data center events ({EVENT_OF_INTEREST.name.replace('_', ' ').lower()})",
#     loc="left", color=INK, fontsize=12,
# )

# Bottom: the treated-minus-control gap with its 95% confidence interval. The pre-period should
# hug zero; that is the parallel-trends check.
gap_axis.fill_between(
    event_time, log_to_pct(event_study["GapLower"]), log_to_pct(event_study["GapUpper"]),
    color=TREATED_COLOR, alpha=0.12, linewidth=0, label="95% confidence interval",
)
gap_axis.plot(event_time, log_to_pct(event_study["Gap"]), color=TREATED_COLOR, linewidth=2, label="Data center zip codes minus comparable zip codes")
gap_axis.axhline(0, color=BASELINE, linewidth=1)
gap_axis.set_ylabel(textwrap.fill("Home value gap (percentage points)", width=25), color=INK, fontweight='bold', fontsize=15)
event_string = 'data center opening' if EVENT_OF_INTEREST == EventOfInterest.FIRST_OPERATIONAL else 'first data center construction headline'
gap_axis.set_xlabel(f"Months relative to {event_string}", color=INK, fontweight='bold', fontsize=15)
gap_axis.legend(frameon=False, loc="lower left")
# Treated zips observed at each point; the count falls off after the anchor as recent events
# run out of data.
for month in range(-EVENT_WINDOW_MONTHS, EVENT_WINDOW_MONTHS + 1, 6):
    gap_axis.annotate(
        f"n={event_study.loc[month, 'N']}", (month, 1), xytext=(0, -4), textcoords="offset points",
        xycoords=("data", "axes fraction"), ha="center", va="top", fontsize=8, color=MUTED,
    )

for axis in (path_axis, gap_axis):
    axis.axvline(0, color=BASELINE, linewidth=1)
    axis.grid(axis="y", color=GRID, linewidth=1)
    axis.tick_params(colors=MUTED, labelcolor=INK)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(BASELINE)
gap_axis.set_xticks(range(-EVENT_WINDOW_MONTHS, EVENT_WINDOW_MONTHS + 1, 6))
plt.savefig('infographic_charts.png', transparent=True) 

HORIZONS_MONTHS = [3, 6, 12]

# The headline numbers: the gap at each fixed horizon after the anchor, in percent, with
# its interval and the number of treated zips observed that far out.
horizon_estimates = event_study.loc[HORIZONS_MONTHS, ["N", "Gap", "GapLower", "GapUpper"]].copy()
for column in ["Gap", "GapLower", "GapUpper"]:
    horizon_estimates[f"{column}Pct"] = log_to_pct(horizon_estimates.pop(column))
horizon_estimates.index.name = "MonthsAfterAnchor"

print(horizon_estimates.round(2).to_string())