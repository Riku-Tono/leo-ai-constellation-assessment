"""Comparison-only single-phase thermal loop sizing for the 100 kW satellite.

All geometry, diameters, roughness, thickness, and efficiencies are design
assumptions. Material density and approximate 60 C water viscosity/density
are independently sourced in the accompanying report.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

Q_TOTAL_W = 100_000.0
LOOPS = 2
CP = 4_000.0  # J/(kg K), comparison assumption retained from mass budget
RHO_FLUID = 983.0  # kg/m3, rounded water value near 60 C
MU = 0.000467  # Pa s, water near 60 C
RHO_PIPE = 8_000.0  # kg/m3, 316L comparison material
THICKNESS = 0.001  # m, assumed nominal wall, not flight-qualified
ROUGHNESS = 0.000015  # m, assumed internal equivalent roughness
ETA_PUMP = 0.50
ETA_MOTOR = 0.90
ETA_DRIVE = 0.95
ETA_TOTAL = ETA_PUMP * ETA_MOTOR * ETA_DRIVE

# Equal paths. For a path, only one module and one panel branch are traversed.
# Header flow is conservatively kept at the full per-loop rate along its 8 m.
SEGMENTS = [
    dict(name="主幹往復", length_path=30.0, count=2, branch_fraction=1.0,
         diameters_mm=(25.0, 32.0, 40.0)),
    dict(name="ヘッダ往復", length_path=8.0, count=2, branch_fraction=1.0,
         diameters_mm=(25.0, 32.0, 40.0)),
    dict(name="放熱パネル枝往復", length_path=10.0, count=8, branch_fraction=0.25,
         diameters_mm=(12.0, 16.0, 20.0)),
    dict(name="計算モジュール枝往復", length_path=3.0, count=10, branch_fraction=0.20,
         diameters_mm=(10.0, 12.0, 16.0)),
]
SIZES = ("細径", "中径", "太径")
DELTAS_K = (5.0, 10.0, 15.0, 20.0)


def friction_factor(re: float, diameter: float) -> float:
    if re < 2300.0:
        return 64.0 / re
    if re < 4000.0:
        raise ValueError("Transition Reynolds range needs separate treatment")
    return 0.25 / math.log10(ROUGHNESS / (3.7 * diameter) + 5.74 / re**0.9)**2


def calc(size: int, delta_k: float) -> dict[str, float | str]:
    mdot_loop = Q_TOTAL_W / LOOPS / (CP * delta_k)
    pipe_mass = 0.0
    fluid_mass = 0.0
    pressure = 0.0
    max_speed = 0.0
    max_hoop = 0.0
    min_re = float("inf")
    contributions = {}
    for s in SEGMENTS:
        diameter = s["diameters_mm"][size] / 1000.0
        outer = diameter + 2.0 * THICKNESS
        length_all = s["length_path"] * s["count"]
        flow = mdot_loop * s["branch_fraction"]
        area = math.pi * diameter**2 / 4.0
        speed = flow / (RHO_FLUID * area)
        re = RHO_FLUID * speed * diameter / MU
        factor = friction_factor(re, diameter)
        dp = factor * s["length_path"] / diameter * RHO_FLUID * speed**2 / 2.0
        wall = RHO_PIPE * math.pi / 4.0 * (outer**2 - diameter**2) * length_all
        fill = RHO_FLUID * area * length_all
        pipe_mass += wall
        fluid_mass += fill
        pressure += dp
        max_speed = max(max_speed, speed)
        min_re = min(min_re, re)
        # At a 1 MPa differential design check, not a pressure-vessel analysis.
        max_hoop = max(max_hoop, 1e6 * diameter / (2 * THICKNESS))
        contributions[s["name"]] = (wall, fill, speed, re, factor, dp)
    electric = LOOPS * pressure * mdot_loop / RHO_FLUID / ETA_TOTAL
    return dict(
        size=SIZES[size], delta_k=delta_k, mdot_loop=mdot_loop,
        max_speed=max_speed, min_re=min_re,
        straight_dp_kpa=pressure / 1000.0,
        pipe_mass_kg=pipe_mass, fluid_mass_kg=fluid_mass,
        partial_mass_kg=pipe_mass + fluid_mass,
        electric_straight_w=electric,
        max_hoop_mpa=max_hoop / 1e6,
        contributions=contributions,
    )


def main() -> None:
    results = [calc(i, d) for d in DELTAS_K for i in range(3)]
    out = Path(__file__).resolve().parent
    keys = [
        "size", "delta_k", "mdot_loop", "max_speed", "min_re",
        "straight_dp_kpa", "pipe_mass_kg", "fluid_mass_kg",
        "partial_mass_kg", "electric_straight_w", "max_hoop_mpa",
    ]
    with (out / "thermal_loop_v01.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row[key] for key in keys})
    for row in results:
        print(
            f"{row['delta_k']:>2.0f}K {row['size']:2s}"
            f" flow={row['mdot_loop']:.3f}kg/s/loop"
            f" vmax={row['max_speed']:.2f}m/s"
            f" dp={row['straight_dp_kpa']:.1f}kPa"
            f" P={row['electric_straight_w']:.0f}W/2loops"
            f" wall={row['pipe_mass_kg']:.1f}kg"
            f" fill={row['fluid_mass_kg']:.1f}kg"
        )
    print("BASE SEGMENTS")
    for name, values in calc(1, 10.0)["contributions"].items():
        print(name, "wall,fill,v,Re,f,dp =", *(round(v, 3) for v in values))


if __name__ == "__main__":
    main()
