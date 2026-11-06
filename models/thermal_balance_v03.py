"""Conditional steady thermal closure for the frozen v0.2 single-phase case.

The radiator uses radiative *effective* area and an assumed area-normalized
fluid-to-surface resistance. This is a screening model, not panel/chip design.
"""
from __future__ import annotations

import csv
from pathlib import Path

SIGMA = 5.670374419e-8  # W/(m2 K4)
EMISSIVITY = 0.85
ABSORBED = 45.0  # W/m2, v0.1/v0.2 scenario assumption
AREA_PANEL = 22.93  # m2 radiative effective area, one main panel
CP = 4000.0  # J/(kg K), comparison assumption
MDOT_PANEL = 0.3125  # kg/s = 1.25 kg/s per loop / 4
HEAT_PANEL = 12_500.0  # W net to reject
HEAT_MODULE = 10_000.0  # W
JUNCTION_LIMIT_C = 95.0


def net_flux(surface_k: float) -> float:
    return EMISSIVITY * SIGMA * surface_k**4 - ABSORBED


def surface_at(fluid_k: float, r_area: float) -> tuple[float, float]:
    """Solve q = (Tf-Ts)/R'' = eps*sigma*Ts^4-q_abs. R'' in m2 K/W."""
    if r_area == 0:
        return fluid_k, net_flux(fluid_k)
    flux = net_flux(fluid_k)
    for _ in range(12):
        surface = fluid_k - r_area * flux
        residual = flux - net_flux(surface)
        derivative = 1 + 4 * EMISSIVITY * SIGMA * r_area * surface**3
        flux -= residual / derivative
        if abs(residual) < 1e-10:
            break
    return fluid_k - r_area * flux, flux


def traverse(inlet_k: float, r_area: float, cells: int = 200) -> tuple[float, float, float, float, float]:
    """Equal effective-area cells, midpoint fluid temperature in each cell."""
    fluid = inlet_k
    area_cell = AREA_PANEL / cells
    total = surface_sum = 0.0
    min_surface, max_surface = float("inf"), -float("inf")
    for _ in range(cells):
        surface, flux = surface_at(fluid, r_area)
        for _ in range(12):
            mid_fluid = fluid - flux * area_cell / (2 * MDOT_PANEL * CP)
            surface, flux_new = surface_at(mid_fluid, r_area)
            if abs(flux_new - flux) < 1e-10:
                break
            flux = flux_new
        fluid -= flux_new * area_cell / (MDOT_PANEL * CP)
        total += flux_new * area_cell
        surface_sum += surface
        min_surface = min(min_surface, surface)
        max_surface = max(max_surface, surface)
    return fluid, total, surface_sum / cells, min_surface, max_surface


def solve(r_area: float, cells: int = 200) -> dict[str, float]:
    """Find coolant inlet that rejects exactly 12.5 kW per panel."""
    lo, hi = 280.0, 450.0
    for _ in range(55):
        inlet = (lo + hi) / 2
        _, rejected, *_ = traverse(inlet, r_area, cells)
        if rejected < HEAT_PANEL:
            lo = inlet
        else:
            hi = inlet
    inlet = (lo + hi) / 2
    outlet, rejected, mean_surface, low_surface, high_surface = traverse(inlet, r_area, cells)
    margin = JUNCTION_LIMIT_C - (inlet - 273.15)
    return {
        "r_area_m2k_w": r_area,
        "panel_inlet_c": inlet - 273.15,
        "panel_outlet_c": outlet - 273.15,
        "panel_net_kw": rejected / 1000,
        "surface_mean_c": mean_surface - 273.15,
        "surface_min_c": low_surface - 273.15,
        "surface_max_c": high_surface - 273.15,
        "junction_margin_k": margin,
        "max_module_r_k_w": margin / HEAT_MODULE,
        "max_per_chip_r_k_w_for_10x1kw": margin / 1000,
    }


def max_r_area_for_junction_drop(chip_drop_k: float) -> float:
    """Maximum assumed panel R'' for a specified hottest-junction drop."""
    lo, hi = 0.0, 0.1
    inlet_limit_k = JUNCTION_LIMIT_C - chip_drop_k + 273.15
    for _ in range(38):
        mid = (lo + hi) / 2
        _, rejected, *_ = traverse(inlet_limit_k, mid)
        if rejected >= HEAT_PANEL:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> None:
    cases = [solve(r) for r in (0.0, 0.005, 0.010, 0.020, 0.030, 0.040)]
    out = Path(__file__).resolve().parent
    with (out / "thermal_balance_v03.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    for case in cases:
        print(f"R''={case['r_area_m2k_w']:.3f} "
              f"in={case['panel_inlet_c']:.2f}C "
              f"out={case['panel_outlet_c']:.2f}C "
              f"surface_mean={case['surface_mean_c']:.2f}C "
              f"junction_margin={case['junction_margin_k']:.2f}K")
    for drop in (0.0, 10.0, 15.0, 20.0, 25.0):
        print(f"chip_drop={drop:.1f}K max_R''={max_r_area_for_junction_drop(drop):.5f}m2K/W")


if __name__ == "__main__":
    main()
