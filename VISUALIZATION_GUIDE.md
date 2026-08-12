# Visualisation & Dashboard Design Guide
### Historical Weather and Climate Variability in Kenya · MIT 8334 Capstone · Group 3
**Deliverable:** `dashboard.py` — an interactive Streamlit dashboard for the Kenya Meteorological Department
**Author of this component:** visualisation & dashboard lead
**Audience for this document:** the group, for the oral defence and the 15-minute video

---

## 1. What this component had to do

The brief asked for **at least five meaningful visualisations that answer the research
questions**, each with a justification, plus **an interactive dashboard** containing
KPI cards, four interactive charts, filters, a geographic map, an executive summary
and drill-down. Rather than build those as two separate things, the dashboard *is* the
delivery vehicle for the visualisations — one artifact, one place to defend.

| Rubric requirement | Where it lives | Count |
|---|---|---|
| ≥ 3 KPI cards | Header row, always visible above the tabs | **5** |
| ≥ 4 interactive charts | Q1–Q5 tabs, map, deep dive | **17** |
| Filters / slicers | Sidebar: counties, study period, dry-day threshold, dry-spell length, smoothing | **5** |
| Geographic map | Executive summary — clickable station map of Kenya | **1** |
| Executive summary | Dedicated first tab, five numbered findings + client actions | ✔ |
| Drill-down | Map click → County deep dive → daily records; table view under every chart | ✔ |
| ≥ 5 visualisations answering the questions | One dedicated tab per research question | ✔ |
| ≥ 3 statistical techniques | Six, documented in the Data & method tab | ✔ |


---

## 2. The method: how each chart was chosen

Charts were not picked by taste. Each one went through the same four steps, in this
order — **the colour decision comes last, which is the opposite of how most dashboards
get built.**

1. **What job does the data have?** Magnitude, identity, polarity, a single headline, or
   change over time. The job selects the form.
2. **What is the form that answers it with the least ink?** If a number answers the
   question, use a number — not a chart.
3. **What can go wrong when someone reads it?** Fix that with labels, ordering, reference
   lines and reading guides before adding decoration.
4. **Only then, colour** — assigned by the role it plays, then *validated* (see §4).

Every chart on the page ships two things beside it, because a chart a client cannot read
is not a deliverable: the **evidence sentence** stating what the chart shows in the client's
terms, with the actual numbers, and a **table view** of the figures behind it, expandable
and downloadable. Encoding notes stay in the chart itself — axis titles, direct labels,
printed cell values and hover — rather than in prose beside it.

---

## 3. Chart-by-chart justification

### Q1 · Which location recorded the highest average annual temperature?

| | |
|---|---|
| **Charts** | (a) Ranked range plot with mean marker · (b) County × year heatmap |
| **Data's job** | Magnitude comparison across places — no time axis in the question |
| **Why this form** | A **sorted** horizontal range plot puts the answer in the reader's first fixation. Sorting is doing analytical work: rank *is* the question. The grey bar (average daily minimum → maximum) answers the question behind the question — heat stress is driven by the hot end of the day, not the average — while the diamond keeps the ranked mean unambiguous. |
| **Alternatives rejected** | A plain bar chart of six means (loses the daily range, so it cannot distinguish persistent heat from a wide diurnal swing). A line chart (implies a trend where the question asks for a ranking). A pie chart (temperature is not a part-to-whole quantity). |
| **Best practices applied** | Ranked, not alphabetical. Values printed in a right-aligned column instead of pinned to markers — a marker-anchored label collided with the maximum-temperature dot on the hot rows. Axis starts at 8 °C, not 0: for temperature, zero is not a meaningful baseline, and the chart is a range plot rather than a length-comparison bar, so no length is being misread. |
| **Second chart** | The heatmap adds the *year* dimension: it shows both the hottest single county-year and, more usefully, that rows are strongly banded — climate zone dominates year-to-year noise, which is the argument for county-specific rather than national planning. |

### Q2 · Which county experienced the greatest annual rainfall variability?

| | |
|---|---|
| **Charts** | (a) Mean-versus-CV quadrant scatter · (b) Box plot of the ten annual totals · (c) Year × county anomaly heatmap |
| **Data's job** | Two measures at once (how much rain, how dependable), then distribution, then polarity |
| **Why this form** | Variability alone is misleading — a large swing matters far more in a dry county than a wet one. The **quadrant scatter** puts both measures on one plot with median reference lines, so "dry *and* erratic" becomes a place on the chart rather than a claim in a sentence. The **box plot with every year drawn as a dot** shows the shape of the variability, not just its summary. The **anomaly heatmap** re-scales each county against its own average so a dry county and a wet one can be compared honestly, and reveals which years hit several counties at once — the national-response years. |
| **Alternatives rejected** | A bar chart of standard deviations (units not comparable across counties). A bar chart of CV alone (hides that Nairobi's high CV sits on a much wetter base). A dual-axis chart plotting mean and CV together (see §6 — never). |
| **Best practices applied** | The scatter uses **one hue with direct text labels**: with six points, text identifies counties better than six colours, and it keeps the chart inside the colour-safe series limit for scatter forms (§4). Quadrant captions are anchored to the plot corners, not to data values, so they can never land on a county. The anomaly scale is **diverging with a neutral grey zero**, because the sign of the departure is the whole point. |

### Q3 · Have average temperatures increased significantly over the past ten years?

| | |
|---|---|
| **Charts** | (a) Annual mean lines with fitted OLS trends · (b) Coefficient plot with 95% confidence intervals |
| **Data's job** | Change over time **and** certainty — two different questions needing two charts |
| **Why this form** | The lines show direction and the size of the year-to-year wobble. The **coefficient plot (forest plot)** is the honest answer to "significantly": a dot for the estimated warming rate, a whisker for its 95% interval, and a vertical line at zero. Every whisker crosses zero, so the reader sees *why* the answer is "not established" without needing to read a p-value column. |
| **Alternatives rejected** | A bar chart of slopes — it implies a precision the data does not support, and invites "Garissa is warming at 0.46 °C/decade" as a finding when its 95% interval spans −0.58 to +1.50. A single national average line (hides that counties differ). Trend arrows or traffic lights (state a verdict without the evidence). |
| **Best practices applied** | Fitted lines are dotted and thin so they never outrank the observed data. Each line is labelled at its end, so identity does not depend on colour matching. The p-value is printed beside each interval. A **caveat box** states the statistical-power limitation in plain language and gives the client the correct reporting line: *this record does not establish a trend*, which is not the same as *there is no warming*. |

### Q4 · Which months consistently record the highest rainfall?

| | |
|---|---|
| **Charts** | (a) Month × county climatology heatmap · (b) National monthly profile bars · (c) Cumulative rainfall curves |
| **Data's job** | A pattern across two categories (month × place), then a headline, then timing |
| **Why this form** | "Consistently, across locations" is precisely what a **heatmap** answers: a dark vertical band *is* consistency, visible in one glance across 72 cells. The bar chart collapses the same data to one axis for the headline number. The **cumulative curve** answers the question water engineers ask next — not *how much* rain, but *when* it arrives and how long the flat stretches are, which is what storage has to bridge. |
| **Alternatives rejected** | A grouped bar chart of 12 months × 6 counties (72 bars, no pattern legible — this was the notebook's exploratory chart and it is the right thing to *replace* in a dashboard). A stacked area by month (implies months accumulate into a meaningful total). A polar/radial "seasonal clock" (looks impressive, reads badly: angle is a poor magnitude channel). |
| **Best practices applied** | Every heatmap cell prints its value in millimetres, so the colour is reinforcement rather than the sole encoding. Colour on the bar chart groups the two rainy seasons and carries no extra measure — and the values are printed on the bars anyway. A caveat box names the counties whose peak falls in a *different* season, which is the finding a national April-focused calendar would erase. |

### Q5 · Which counties appear most vulnerable to drought or prolonged dry periods?

| | |
|---|---|
| **Charts** | (a) Ranked composite index bars · (b) Component matrix · (c) Dry-spell timeline |
| **Data's job** | A constructed measure — so the visualisation must expose the construction, not just the verdict |
| **Why this form** | Vulnerability is not measured, it is *built* from four strands (aridity, variability, dry-spell persistence, heat stress). One ranked bar answers **who**. The **component matrix** answers **on what grounds**, and reading down its columns separates two genuinely different problems: dark on aridity + persistence is a water-supply problem (storage, boreholes); dark on variability alone is a predictability problem (forecasting, index insurance, flexible planting). The **dry-spell timeline** is the raw evidence in original units — every unbroken dry run of 21+ days placed on a real date axis. Garissa's row is a dense wall, and that single image makes "dryness is the normal state, not an event" undeniable. |
| **Alternatives rejected** | A radar/spider chart of the four strands (area is not comparable, axis order changes the shape, and it hides the raw values). A single stacked bar of the four components (they have different units — stacking them would be meaningless arithmetic on screen). Index only, with no components (asks the client to trust a black box). |
| **Best practices applied** | The index is **min–max scaled within the counties on screen** and the caveat says so: 0 and 100 mean "least and most vulnerable *of this group*", not an absolute national score. Equal weighting is stated as the default it is, and the component matrix lets the client re-weight by inspection. Tier colours come from a reserved status palette and every bar is labelled with its tier name, so the tier never depends on colour alone. The timeline's colour ramp starts one step in from the lightest blue, because those bars are thin and the faintest step would vanish into the surface. |

### Geographic map (executive summary)

Bubble **area** encodes average annual rainfall and bubble **colour** encodes whichever
measure the reader selects — two channels for two measures, so there is never a second
y-axis. Every bubble is labelled with its county name. The size floor is deliberately
generous: the driest county is also the highest-risk one, and it must not end up as the
least visible mark on the map. Built on Plotly's native geographic layer (country
borders, coastline and Lake Victoria drawn from built-in geometry) rather than tiled
basemap imagery, so **the map still renders with no internet connection** — a
presentation-day insurance policy.

### County deep dive (drill-down)

Clicking a bubble on the map sets the county here; the daily record is then shown as
**two stacked charts sharing one date axis** — temperature above, monthly rainfall
anomaly below — rather than one chart with two y-scales (§6). A correlation matrix and
the full daily table sit behind expanders, which is where an auditor can check any
aggregate on any other tab.

---

## 4. The colour system, and why it is computed rather than chosen

Colour was assigned by the **job** it does, never by preference:

| Job | Encoding used | Where |
|---|---|---|
| **Identity** (which county) | 6 categorical hues, fixed order | Trend lines, box plots, cumulative curves |
| **Magnitude** (how much) | One hue, light → dark | Temperature, climatology, component matrix, dry-spell length |
| **Polarity** (above/below normal) | Two hues + neutral grey midpoint | Rainfall anomaly, correlation matrix |
| **State** (risk tier) | Reserved status palette + icon + label | Vulnerability index, map tiers |

**The categorical palette was run through a colour-vision-deficiency validator before any
chart code was written.** Results on the light chart surface:

- Worst adjacent-pair separation under protanopia: **ΔE 9.1** (target ≥ 8) ✔
- Worst adjacent-pair separation for normal vision: **ΔE 19.6** (floor ≥ 15) ✔
- All six hues inside the required lightness band and above the chroma floor ✔
- Three of the six sit below 3:1 contrast against the surface → **relief required**

That last line is why every chart in this dashboard has direct labels and a table view.
It is not decoration; it is the documented mitigation for a measured contrast shortfall.

Two rules follow from the same validation and are visible throughout:

- **Colour follows the county, never its rank.** Filtering counties out never repaints the
  survivors, so a colour means the same thing on every tab and in every filter state.
- **Scatter, bubble and map forms carry a series cap.** In those forms every pair of
  colours is compared simultaneously, and six hues cannot clear the separation floors
  under that condition — so the quadrant scatter uses **one hue plus text labels**
  instead. This is why Q2's lead chart looks deliberately monochrome: it is the correct
  answer to a measurable constraint, not a missed opportunity for colour.

---

## 5. Visualisation best practices applied 

| Practice | How it shows up here |
|---|---|
| The chart type follows the data's job | §3 documents the job and the form for each |
| Sorted, not alphabetical | Q1 ranking, Q5 index, dry-spell timeline all ordered by value |
| Direct labelling over legend-hunting | Line ends, bubble labels, printed cell values, value columns, tier names on bars |
| Legend present for every multi-series chart | Placed **below** the plot — a top-anchored legend collided with the title |
| Reference lines carry meaning | Medians (Q2), zero (Q3), each county's own average (deep dive) |
| Recessive chrome | Hairline gridlines, muted axis ink, no chart borders or shadows |
| Thin marks, gaps between fills | 2 px gaps between heatmap cells, 0.6 bar width, rounded bar ends |
| Values readable on every fill | Cell labels flip to white on the dark end of the ramp |
| Hover on every chart | Units, county name and date in every tooltip |
| An accessible table for every chart | Expandable table + CSV download under each one |
| Consistent ordering between paired charts | Q5's index bars and component matrix share one row order |
| Uncertainty shown, not hidden | 95% intervals (Q3), all ten years plotted as dots (Q2) |
| Honest scaling stated in words | Relative index caveat, CV-versus-SD explanation, per-county anomaly baseline |

---

## 6. Anti-patterns deliberately avoided

These are worth naming out loud in the video, because avoiding them was a design
decision rather than an oversight:

1. **No dual-axis charts.** Temperature and rainfall never share one frame with two
   y-scales. Two measures on two scales let a reader invent a correlation by rescaling —
   the single most common chart mistake. Where both are needed, the deep dive **stacks
   two charts on one shared date axis** instead.
2. **No rainbow colour scales.** Magnitude gets one hue, light to dark; a rainbow ramp
   creates false boundaries where the data is smooth.
3. **No hue at a diverging midpoint.** The anomaly scale passes through neutral grey, so
   "no departure from normal" reads as nothing rather than as a third category.
4. **No pie or donut charts.** No question here is part-to-whole, and angle is a weak
   magnitude channel.
5. **No colour-only encoding anywhere.** Every risk tier carries an icon and a word;
   every heatmap cell prints its number; every line and bubble is labelled.
6. **No truncated bar baselines.** Bars that encode magnitude by length (rainfall,
   vulnerability index) start at zero. The one chart that starts elsewhere is a *range*
   plot, where no length is being compared.
7. **No 3-D, no shadows, no gradients on data marks.**
8. **No implied precision.** Slopes appear with intervals; a composite index appears with
   its components; "not significant" is never rendered as "no change".

---

## 7. Statistical honesty

1. **The warming answer is a null result, and it is presented as one.** Zero of six
   counties show a significant trend (all p > 0.05). The dashboard says this is a
   statement about a ten-point series with low statistical power, **not** evidence that
   Kenya is not warming, and recommends re-testing on a 30-year window. Presenting the
   confidence intervals rather than the slopes is what makes that reading unavoidable.
2. **CV rather than standard deviation** for rainfall variability, because the counties
   differ threefold in average rainfall — a ±450 mm swing is routine in Mombasa and
   catastrophic in Garissa. Both statistics are in the table.
3. **The vulnerability index is relative and says so.** Min–max scaling within the six
   counties means Garissa scores 100 because it is worst *here*, on all four strands —
   not because it hit an absolute threshold.

**The data-quality assessment found nothing to
repair** — 21,918 rows, zero duplicates, zero missing values, zero physically implausible
values, 100% calendar completeness. That is expected of a reanalysis product (ERA5 is
modelled onto a regular grid rather than read off instruments), and the Data & method tab
shows the tests that were run, because "we found no problems" is only credible when the
tests are visible.

---

## 8. Running it

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

The app loads `data/cleaned/kenya_weather_cleaned.csv` if the notebook has produced it,
falls back to the raw JSON in `data/raw/`, and if neither exists calls the Open-Meteo
archive API itself and writes both — so it runs on a clean machine or on Streamlit
Community Cloud with no manual setup. `.streamlit/config.toml` pins the light theme,
because the palette was validated against a light surface and the contrast results only
hold against the surface the chart actually renders on.

---

## 9. Files in this component

| File | What it is |
|---|---|
| `dashboard.py` | The complete dashboard — data loading, cleaning, analytics, and all 17 charts |
| `requirements.txt` | Dependencies |
| `.streamlit/config.toml` | Light theme pin + palette tokens |
| `VISUALIZATION_GUIDE.md` | This document |
| `data/raw/*.json` | Raw API responses, one per county |
| `data/cleaned/kenya_weather_cleaned.csv` | Cleaned dataset (21,918 rows) |
