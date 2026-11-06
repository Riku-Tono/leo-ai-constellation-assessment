"""Comparison-only v0.2: equal-flow targets in direct-return headers.

All geometry and fluid/component values are assumptions, not flight design.
The 8 m/loop header inventory of v0.1 is preserved: 4 m computer side,
4 m radiator side; each side has equal-length supply and return pipes.
"""
from __future__ import annotations

import csv
import math
from itertools import product
from pathlib import Path

Q_W = 100_000.0
CP = 4_000.0
RHO = 983.0
MU = 0.000467
RHO_PIPE = 8_000.0
WALL = 0.001
ROUGHNESS = 0.000015
ETA = 0.50 * 0.90 * 0.95
SIZES = {
    "細径": (0.025, 0.012, 0.010),
    "中径": (0.032, 0.016, 0.012),
    "太径": (0.040, 0.020, 0.016),
}


def loss(length: float, diameter: float, mdot: float) -> float:
    area = math.pi * diameter**2 / 4
    speed = mdot / (RHO * area)
    re = RHO * speed * diameter / MU
    if re < 2300:
        factor = 64 / re
    elif re >= 4000:
        factor = 0.25 / math.log10(ROUGHNESS / (3.7 * diameter) + 5.74 / re**0.9) ** 2
    else:
        raise ValueError(f"transition Reynolds number {re:.0f}")
    return factor * length / diameter * RHO * speed**2 / 2


def header_paths(branches: int, diameter: float, mdot_loop: float) -> list[float]:
    """Direct-return topology; 2 m supply + 2 m return per side/loop.

    For branch k, both headers traverse segments 1..k. Segment j carries
    (n-j+1)/n of loop flow. Identical supply and return fractions are an
    explicit topology assumption; changing return routing changes results.
    """
    segment_length = 2.0 / branches
    return [sum(2 * loss(segment_length, diameter,
                         mdot_loop * (branches - j + 1) / branches)
                for j in range(1, k + 1)) for k in range(1, branches + 1)]


def mass(length: float, diameter: float) -> tuple[float, float]:
    area = math.pi * diameter**2 / 4
    outer = diameter + 2 * WALL
    return (RHO_PIPE * math.pi / 4 * (outer**2 - diameter**2) * length,
            RHO * area * length)


def calculate(size: str, delta_k: float) -> tuple[dict, list[dict]]:
    trunk_d, panel_d, module_d = SIZES[size]
    mdot = Q_W / 2 / (CP * delta_k)
    trunk = loss(30, trunk_d, mdot)
    panel_branch = loss(10, panel_d, mdot / 4)
    module_branch = loss(3, module_d, mdot / 5)
    computer = header_paths(5, trunk_d, mdot)
    radiator = header_paths(4, trunk_d, mdot)
    max_c, max_r = max(computer), max(radiator)
    rows = []
    for c, r in product(range(5), range(4)):
        bare = trunk + module_branch + computer[c] + panel_branch + radiator[r]
        add_computer = max_c - computer[c]
        add_radiator = max_r - radiator[r]
        rows.append(dict(size=size, delta_k=delta_k, computer_branch=c + 1,
                         radiator_branch=r + 1, computer_header_kpa=computer[c] / 1000,
                         radiator_header_kpa=radiator[r] / 1000,
                         bare_path_kpa=bare / 1000,
                         computer_balance_kpa=add_computer / 1000,
                         radiator_balance_kpa=add_radiator / 1000,
                         total_balance_kpa=(add_computer + add_radiator) / 1000,
                         equalized_path_kpa=(bare + add_computer + add_radiator) / 1000))
    wall, fill = (0.0, 0.0)
    for length, diameter in ((60, trunk_d), (16, trunk_d),
                             (80, panel_d), (30, module_d)):
        w, f = mass(length, diameter)
        wall += w
        fill += f
    head = trunk + module_branch + max_c + panel_branch + max_r
    return dict(size=size, delta_k=delta_k, mdot_loop=mdot,
                trunk_kpa=trunk / 1000, module_branch_kpa=module_branch / 1000,
                computer_header_max_kpa=max_c / 1000,
                panel_branch_kpa=panel_branch / 1000,
                radiator_header_max_kpa=max_r / 1000,
                bare_min_kpa=min(row["bare_path_kpa"] for row in rows),
                equalized_path_kpa=head / 1000,
                electric_target_w=2 * head * mdot / RHO / ETA,
                wall_kg=wall, fill_kg=fill, partial_mass_kg=wall + fill), rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    all_cases, base_paths = [], []
    for delta in (5.0, 10.0, 15.0, 20.0):
        for size in SIZES:
            case, paths = calculate(size, delta)
            all_cases.append(case)
            if size == "中径" and delta == 10.0:
                base_paths = paths
    out = Path(__file__).resolve().parent
    write_csv(out / "thermal_loop_v02.csv", all_cases)
    write_csv(out / "thermal_paths_v02.csv", base_paths)
    for case in all_cases:
        print(f"{case['delta_k']:2.0f}K {case['size']} "
              f"head={case['equalized_path_kpa']:.2f}kPa/loop "
              f"power={case['electric_target_w']:.1f}W/2loops "
              f"mass={case['partial_mass_kg']:.1f}kg")


if __name__ == "__main__":
    main()
