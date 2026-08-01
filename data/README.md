# Getting the data

This project runs on the **Marketing & E-Commerce Analytics Dataset** by
Geetha Sagar Bonthu, published on Kaggle:

https://www.kaggle.com/datasets/geethasagarbonthu/marketing-and-e-commerce-analytics-dataset

License: [CC0: Public Domain](https://creativecommons.org/publicdomain/zero/1.0/)

Citation:
> Geetha Sagar Bonthu. (2025). Marketing & E-Commerce Analytics Dataset [Dataset]. Kaggle. https://doi.org/10.34740/KAGGLE/DSV/13964291

The raw CSVs are **not committed to this repo** — `events.csv` alone is
~180MB, well past what belongs in a git repo, and it's better practice to
point at the canonical source than to vendor a copy.

## Setup

1. Download the dataset from the Kaggle link above (Download button, top
   right of the page — sign in if prompted).
2. Unzip it.
3. Copy all five CSVs into `data/raw/` in this project:

```
data/raw/
├── customers.csv
├── products.csv
├── campaigns.csv
├── transactions.csv
└── events.csv
```

4. Run the pipeline: `python -m src.pipeline` (see the main README for the
   full sequence).

## What's in each file

| File | Rows | Grain |
|---|---:|---|
| `customers.csv` | 100,000 | one row per customer |
| `products.csv` | 2,000 | one row per product |
| `campaigns.csv` | 50 | one row per marketing campaign |
| `transactions.csv` | 103,127 | one row per completed purchase |
| `events.csv` | 2,000,000 | one row per user interaction (view/click/add_to_cart/bounce/purchase) |

Two real data-quality quirks in `events.csv` that this project handles
explicitly rather than glossing over (see the main README's "Design
decisions" section for the reasoning):

- `session_id` is not a reliable single-visit identifier — the same value
  frequently appears across different customers and across dates years
  apart. This project derives its own sessions from timestamps instead.
- `experiment_group` (Control / Variant_A / Variant_B) is assigned
  independently per event rather than persisted per customer, so it can't
  be read as a traditional sticky user-level A/B cohort. This project
  analyzes it at the event level instead, with that limitation documented.
