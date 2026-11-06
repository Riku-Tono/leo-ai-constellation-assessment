# Model files and historical study notes

Current assessment: [English](../README.md) / [日本語](../ja/README.md).

The original model files and Japanese notes were restored from the
2026-10-05 distribution archive. Their assumptions and numerical outputs are
historical snapshots. See [SNAPSHOT.txt](SNAPSHOT.txt) for provenance.

Run the added comparison from the repository root:

```bash
python models/google_update_20261106.py
```

This produces the [radiation comparison](google_update_radiation_20261106.csv),
[junction comparison](google_update_junction_20261106.csv), and
[temperature boundaries](google_update_limits_20261106.csv).

The 50°C radiation-area calculation and the original geometry's junction
temperature comparison are separate evaluations. Refer to the current guides
for their assumptions, sources, and limits.
