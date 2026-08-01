# ab_test.R
#
# R equivalent of src/ab_testing.py's headline test: a 3-group chi-squared
# test across Control / Variant_A / Variant_B on purchase-vs-not at the
# event level, followed by pairwise 2-sample proportion tests with a
# Bonferroni correction. See src/ab_testing.py's module docstring for why
# the event level is the right unit here (experiment_group is assigned
# per-event, not persisted per customer) and for the customer-clustered
# bootstrap robustness check, which this script does not duplicate.
#
# Usage:
#   Rscript analysis/ab_test.R path/to/warehouse.db
#
# Requires: DBI, RSQLite (install.packages(c("DBI", "RSQLite")))

args <- commandArgs(trailingOnly = TRUE)
db_path <- if (length(args) >= 1) args[1] else "data/processed/warehouse.db"

suppressPackageStartupMessages({
  library(DBI)
  library(RSQLite)
})

con <- dbConnect(RSQLite::SQLite(), db_path)

totals <- dbGetQuery(con, "
  SELECT experiment_group,
         COUNT(*) AS total_events,
         SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchase_events
  FROM fct_events
  GROUP BY experiment_group
")
dbDisconnect(con)

rownames(totals) <- totals$experiment_group
totals <- totals[c("Control", "Variant_A", "Variant_B"), ]
totals$purchase_rate <- totals$purchase_events / totals$total_events

cat("=== Purchase rate by experiment_group ===\n")
print(totals)

# 3-group chi-squared test
tbl <- rbind(totals$purchase_events, totals$total_events - totals$purchase_events)
colnames(tbl) <- totals$experiment_group
chi_result <- chisq.test(tbl, correct = FALSE)
cat("\n=== 3-group chi-squared test ===\n")
print(chi_result)

# Pairwise proportion tests with Bonferroni correction
pairs <- list(c("Control", "Variant_A"), c("Control", "Variant_B"), c("Variant_A", "Variant_B"))
alpha_bonf <- 0.05 / length(pairs)
cat(sprintf("\n=== Pairwise tests (Bonferroni alpha = %.4f) ===\n", alpha_bonf))

for (pair in pairs) {
  a <- pair[1]; b <- pair[2]
  test <- prop.test(
    x = c(totals[a, "purchase_events"], totals[b, "purchase_events"]),
    n = c(totals[a, "total_events"], totals[b, "total_events"]),
    correct = FALSE
  )
  lift_pp <- 100 * (totals[b, "purchase_rate"] - totals[a, "purchase_rate"])
  cat(sprintf(
    "%s vs %s: lift=%.2fpp, p=%.4g, significant=%s\n",
    a, b, lift_pp, test$p.value, ifelse(test$p.value < alpha_bonf, "YES", "no")
  ))
}
