# Pending transfer of original artifacts

The author-provided review bundle `pqc-mtls-github-ready.zip` contains the historical sanitized `wrk` logs, intermediate and consolidated CSVs, the original portable Matplotlib plotting scripts, and all eight original figures in PNG, SVG and PDF. It was audited offline before this GitHub branch was created.

The currently connected GitHub publishing interface can commit source and numeric data but does not directly import the ZIP's binary chart files. This branch therefore contains numerical CSV results, reproducibility code and fresh SVG previews **only**. Original chart files, source logs, Apache virtual hosts, `wrk-mtls` patch, exporter source and raw Prometheus series remain pending. No claim is made that they have already been committed.

To add the exact original artifacts on a workstation, download/unzip the prepared review bundle and copy the `mtls/` tree into the cloned repository, inspect `git diff` for overlapping files and ensure the new source files replace only those intended. Review for private keys and internal infrastructure details before committing. Retain the primary November 2026 HTTPS benchmark unchanged.
