# Data Quality Assessment

Raw rows loaded: 21918
Locations: 6 (Eldoret, Garissa, Kisumu, Mombasa, Nairobi, Nakuru)

## Missing values (NaNs in existing rows)
- temperature_2m_max: 0
- temperature_2m_min: 0
- temperature_2m_mean: 0
- precipitation_sum: 0
- rain_sum: 0
- windspeed_10m_max: 0

## Missing dates (gaps in the expected daily sequence)
- Nairobi: 0 missing day(s) (0.00% of expected range)
- Kisumu: 0 missing day(s) (0.00% of expected range)
- Mombasa: 0 missing day(s) (0.00% of expected range)
- Eldoret: 0 missing day(s) (0.00% of expected range)
- Nakuru: 0 missing day(s) (0.00% of expected range)
- Garissa: 0 missing day(s) (0.00% of expected range)

## Duplicate records (same location + date)
- 0 duplicate row(s) found across all locations

## Outliers (values outside physically plausible ranges for Kenya)
- 0 row(s) contain at least one implausible value

## Data completeness (% of expected days actually present, per location)
- Nairobi: 3653/3653 days (100.00%)
- Kisumu: 3653/3653 days (100.00%)
- Mombasa: 3653/3653 days (100.00%)
- Eldoret: 3653/3653 days (100.00%)
- Nakuru: 3653/3653 days (100.00%)
- Garissa: 3653/3653 days (100.00%)

## Consistency across locations
- temperature_2m_max: float64
- temperature_2m_min: float64
- temperature_2m_mean: float64
- precipitation_sum: float64
- rain_sum: float64
- windspeed_10m_max: float64
All dates fall within 2015-01-01–2024-12-31: True

## Cleaning decisions applied

- Dropped 0 duplicate row(s), kept first occurrence. Duplicates would double-count those days in aggregation.
- Converted 0 physically implausible value(s) to missing rather than dropping the whole row, since the other variables that day are still usable.
- Reindexed every location to the full daily calendar so missing days become explicit rows rather than silently absent.
- Linearly interpolated gaps of 3 day(s) or fewer per location per variable. Longer gaps are left as NaN rather than guessed. 0 value(s) remain missing.
- Schema and units were already consistent across locations (°C, mm, km/h); only column order/naming was standardized.

Cleaned dataset exported to data/cleaned/kenya_weather_cleaned.csv (21918 rows, 6 locations).
