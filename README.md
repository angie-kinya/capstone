[Open in Google Colab] here 👇

(https://colab.research.google.com/drive/1aeHsI9Jg9ThBwFO3PQvWjX3hJjLeKOcw?usp=sharing),

to colaborate on this file
Next stages: Statistical Analysis, Visualization & Dashboard and  Recommendations & Presentation Lead





# Historical Weather and Climate Variability in Kenya
A data pipeline that fetches, assesses, and cleans 10 years of daily historical weather data across six Kenyan cities, producing a clean, analysis-ready dataset alongside a full data-quality report.

📓 **Notebook:** `Copy_of_Capstone_Project_Group_3.ipynb`
▶️ **Open in Colab:** [Insert your Google Drive/Colab link here]

---

## Overview

This project pulls daily historical weather data from the [Open-Meteo Archive API](https://archive-api.open-meteo.com/v1/archive) for six locations across Kenya, spanning **January 1, 2015 – December 31, 2024**. The notebook is organized as an end-to-end pipeline:

1. **Acquire** raw weather data from the API
2. **Load** all locations into a single DataFrame
3. **Assess** data quality (missing values, gaps, duplicates, outliers, completeness, consistency)
4. **Clean** the data based on those findings
5. **Export** the cleaned dataset and a written data-quality report
6. **Package** everything for submission

## Locations Covered

| City | Latitude | Longitude |
|------|----------|-----------|
| Nairobi | -1.2921 | 36.8219 |
| Kisumu | -0.0917 | 34.7680 |
| Mombasa | -4.0435 | 39.6682 |
| Eldoret | 0.5143 | 35.2698 |
| Nakuru | -0.3031 | 36.0800 |
| Garissa | -0.4536 | 39.6401 |

## Weather Variables

- `temperature_2m_max` — daily maximum temperature (°C)
- `temperature_2m_min` — daily minimum temperature (°C)
- `temperature_2m_mean` — daily mean temperature (°C)
- `precipitation_sum` — total daily precipitation (mm)
- `rain_sum` — total daily rainfall (mm)
- `windspeed_10m_max` — maximum daily windspeed at 10m (km/h)

## Notebook Structure

| Section | What it does |
|---|---|
| **Setup** | Imports, location coordinates, date range, variable list, plausible-value ranges, output folders, logging utility |
| **Step 1 — Data Acquisition** | Calls the Open-Meteo API per location, with automatic retry/backoff on rate limits; saves raw JSON to `data/raw/` |
| **Step 2 — Load into One DataFrame** | Reads the saved JSON files and combines all six locations into one long-format table |
| **Step 3 — Data Quality Assessment** | Broken into sub-sections 3.1–3.7: overview, missing values, missing dates, duplicate records, outliers, completeness %, and consistency checks — each logged individually, then packaged into a reusable `assess_quality()` function |
| **Step 4 — Data Cleaning** | Broken into sub-sections 4.1–4.5: remove duplicates, convert implausible values to missing, reindex to the full daily calendar, interpolate short gaps (≤3 days), and finalize column order — packaged into a reusable `clean_data()` function |
| **Step 5 — `main()`** | Runs the entire pipeline end-to-end in one call: acquire → load → assess → clean → export |
| **Step 6 — Package Outputs** | Bundles the raw data, cleaned CSV, and quality report into `group3_outputs.zip` for submission |

## Cleaning Rules Applied

- **Duplicates:** rows with the same `location` + `date` are dropped, keeping the first occurrence.
- **Outliers:** values outside physically plausible ranges for Kenya (e.g. max temp outside 5–45°C, windspeed outside 0–120 km/h) are converted to `NaN` rather than dropping the whole row, so other variables recorded that day stay usable.
- **Missing dates:** every location is reindexed against the full expected daily calendar, so missing days become explicit rows instead of silently disappearing.
- **Short gaps:** gaps of 3 days or fewer, per location per variable, are filled with linear interpolation. Longer gaps are left as `NaN` rather than guessed at.

Every decision made during assessment and cleaning is logged and exported to `DATA_QUALITY_ASSESSMENT.md`.

## Requirements

- Python 3.x
- `pandas`
- `numpy`
- `requests`

No installation needed if running in **Google Colab** — all dependencies are pre-installed.

## How to Run

1. Open the notebook in Google Colab (link above), or upload it to your own Colab/Jupyter environment.
2. Run all cells top to bottom (**Runtime → Run all** in Colab).
3. The first run will call the Open-Meteo API (~6 locations × 10 years), which may take a few minutes and can pause briefly if rate-limited — this is handled automatically with retries.
4. On subsequent runs, `acquire_all()` skips any location whose raw JSON is already saved locally, so it resumes instead of re-fetching everything.

## Output Files

| File | Description |
|---|---|
| `data/raw/*.json` | Raw API response per location |
| `data/cleaned/kenya_weather_cleaned.csv` | Final cleaned dataset (all locations, all variables) |
| `DATA_QUALITY_ASSESSMENT.md` | Full written log of every assessment finding and cleaning decision |
| `group3_outputs.zip` | All of the above, bundled for submission |

## Notes / Troubleshooting

- Re-running the packaging step (Step 6) after it has already run once will raise a `FileExistsError` on `shutil.copytree`, since `group3_outputs/data` already exists. Delete the `group3_outputs/` folder first, or add `dirs_exist_ok=True` / clear it programmatically before re-running.
- If a cell references `df` or `cleaned_df` and raises a `NameError`, make sure the earlier "Run the pipeline" cell (Step 2) has been executed first — cells depend on variables created upstream, so running out of order will break later steps.

## Contributors

- Group 3
