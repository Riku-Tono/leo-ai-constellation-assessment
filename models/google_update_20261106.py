"""Reproduce the 2026-11-06 comparisons using Python 3.10+ (stdlib only).

50 C is an illustrative radiator temperature in the Joule paper, not a
measured spacecraft operating point. The original study's emissivity, external
absorption, 100 kW AI load and 85% compute allocation remain assumptions.

The radiation-area comparison and the unchanged-geometry junction comparison
are separate calculations. This script does not redesign the radiator, infer
HBM temperature from silicon junction temperature, or estimate complete mass.

Sources and scope are documented in the current English/Japanese README files.
"""
from __future__ import annotations

import csv
from pathlib import Path

import thermal_structure_v04 as original


OUT = Path(__file__).resolve().parent
AI_POWER_W = 100_000.0
COMPUTE_FRACTION = 0.85
EMISSIVITY = 0.85
ABSORBED_W_M2 = 45.0


def radiation_cases() -> list[dict]:
    total_w = AI_POWER_W / COMPUTE_FRACTION
    cases = []
    for name, temp_c in (("original_59p5C", 59.5), ("comparison_50C", 50.0)):
        temp_k = temp_c + 273.15
        net_w_m2 = EMISSIVITY * original.SIGMA * temp_k**4 - ABSORBED_W_M2
        if net_w_m2 <= 0:
            raise ValueError("No positive net radiative heat rejection")
        cases.append(dict(
            case=name, ai_power_w=AI_POWER_W, total_heat_w=total_w,
            radiator_temperature_c=temp_c, emissivity=EMISSIVITY,
            absorbed_w_m2=ABSORBED_W_M2, net_rejection_w_m2=net_w_m2,
            effective_radiating_area_m2=total_w / net_w_m2,
        ))
    baseline = cases[0]["effective_radiating_area_m2"]
    for row in cases:
        row["area_increase_percent"] = (
            row["effective_radiating_area_m2"] / baseline - 1
        ) * 100
    return cases


def junction_cases() -> list[dict]:
    # Preserve the original 8 x 22.93 m2 geometry, flow and 500 W sources.
    # Surface temperature is solved here; it is not prescribed as 50 C.
    panel = original.panel(32)
    chip = original.chip(160)
    cases = []
    for absorbed in (45.0, 100.0):
        solved = original.solve(panel, chip, absorbed)
        cases.append(dict(
            panel_tubes=32, chip_channels=160, heat_per_source_w=500.0,
            main_effective_area_m2=8 * original.AREA,
            absorbed_w_m2=absorbed, junction_c=solved["junction_c"],
            solved_mean_surface_c=solved["surface_mean_c"],
            margin_to_historical_95_k=95 - solved["junction_c"],
            margin_to_comparison_90_k=90 - solved["junction_c"],
            margin_to_85_target_k=85 - solved["junction_c"],
            main_heat_kw=solved["main_heat_kw"],
            remaining_aux_heat_kw=solved["remaining_aux_heat_kw"],
            pump_electric_w=solved["pump_electric_w"],
        ))
    return cases


def limit_cases() -> list[dict]:
    panel = original.panel(32)
    chip = original.chip(160)
    return [dict(
        panel_tubes=32, chip_channels=160,
        junction_target_c=target,
        reserve_below_90_k=90 - target,
        max_absorbed_w_m2=original.absorbed_limit(panel, chip, target),
    ) for target in (90.0, 85.0)]


def write_csv(filename: str, rows: list[dict]) -> None:
    with (OUT / filename).open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    radiation = radiation_cases()
    junction = junction_cases()
    limits = limit_cases()
    write_csv("google_update_radiation_20261106.csv", radiation)
    write_csv("google_update_junction_20261106.csv", junction)
    write_csv("google_update_limits_20261106.csv", limits)
    for row in radiation:
        print(f"{row['case']}: area={row['effective_radiating_area_m2']:.3f} m2, "
              f"change={row['area_increase_percent']:.3f}%")
    for row in junction:
        print(f"Unchanged geometry, absorbed={row['absorbed_w_m2']:.0f} W/m2: "
              f"Tj={row['junction_c']:.3f} C, "
              f"margin below 90 C={row['margin_to_comparison_90_k']:.3f} K")
    for row in limits:
        print(f"Tj target={row['junction_target_c']:.0f} C: "
              f"absorbed boundary={row['max_absorbed_w_m2']:.3f} W/m2")


if __name__ == "__main__":
    main()
