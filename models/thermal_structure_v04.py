"""Geometry-based comparison model, not a flight-qualified thermal design.

Fixed comparison water properties near 60 C; material conductivities and all
dimensions are explicit design assumptions. Known internal-channel losses
replace part of v0.2's unknown losses. Main-loop pump heat is relocated from
the existing 17.65 kW auxiliary budget, never added again to global power.
"""
from __future__ import annotations
import csv
import math
import os
from pathlib import Path

SIGMA, RHO, MU, CP, KF = 5.670374419e-8, 983.0, 0.000467, 4000.0, 0.653
AREA, WIDTH, MDOT_LOOP, ETA = 22.93, 2.5, 1.25, 0.4275
KNOWN_EXTERNAL_DP = 59_578.7907437945


def circular_channel(mdot: float, diameter: float, length: float) -> dict:
    speed = mdot / (RHO * math.pi * diameter**2 / 4)
    re = RHO * speed * diameter / MU
    if re < 4000:
        raise ValueError("Panel correlation requires turbulent flow Re >= 4000")
    f = (0.79 * math.log(re) - 1.64) ** -2
    pr = CP * MU / KF
    nu = (f / 8 * (re - 1000) * pr /
          (1 + 12.7 * math.sqrt(f / 8) * (pr ** (2 / 3) - 1)))
    return dict(re=re, h=nu * KF / diameter, speed=speed,
                dp=f * length / diameter * RHO * speed**2 / 2)


def panel(tubes: int) -> dict:
    length, pitch, di, do = AREA / WIDTH, WIDTH / tubes, 0.006, 0.008
    water = circular_channel(MDOT_LOOP / 4 / tubes, di, length)
    k_skin, thickness, k_tube = 160.0, 0.001, 160.0
    # 0.1 mm bonding layer, k=5 W/mK, 6 mm continuous contact width.
    conv = pitch / (water["h"] * math.pi * di)
    wall = pitch * math.log(do / di) / (2 * math.pi * k_tube)
    bond = pitch * 0.0001 / (5 * 0.006)
    # Thin strip between adjacent tube lines, uniform sink approximation.
    spread = pitch**2 / (12 * k_skin * thickness)
    tube_length = tubes * length
    return dict(tubes=tubes, pitch_m=pitch, length_m=length,
                re=water["re"], h_w_m2k=water["h"], dp_pa=water["dp"],
                r_conv=conv, r_wall=wall, r_bond=bond, r_spread=spread,
                r_area=conv + wall + bond + spread,
                tube_length_m=tube_length,
                tube_wall_kg=2700 * math.pi / 4 * (do**2 - di**2) * tube_length,
                tube_fill_kg=RHO * math.pi / 4 * di**2 * tube_length)


def chip(channels: int = 120, tim_um: float = 50, nu: float = 3.09,
         chips_per_module: int = 20) -> dict:
    # 20 identical 500 W sources/module; 10 modules; independent equal-flow
    # chip branches. The 40 x 40 mm source is uniform, not a real AI package.
    heat, source_area, source_side = 10000 / chips_per_module, 0.04**2, 0.04
    channel_side, length = 0.0002, 0.04
    mdot = 0.250 / chips_per_module / channels
    speed = mdot / (RHO * channel_side**2)
    re = RHO * speed * channel_side / MU
    if re >= 2300:
        raise ValueError("Microchannels must remain in assumed laminar regime")
    # Darcy f for fully developed square duct (not circular 64/Re).
    friction = 56.91 / re
    dp = friction * length / channel_side * RHO * speed**2 / 2
    h = nu * KF / channel_side
    fin_width = source_side / channels - channel_side
    if fin_width <= 0:
        raise ValueError("Channels exceed footprint")
    m_height = math.sqrt(2 * h / (180 * fin_width)) * channel_side
    fin_eta = math.tanh(m_height) / m_height
    # Bottom plus two conducting side walls; unheated roof excluded.
    wetted_effective = channels * length * (channel_side + 2 * channel_side * fin_eta)
    terms = {
        "silicon": 0.0003 / (120 * source_area),
        "copper_lid": 0.002 / (390 * source_area),
        "tim": tim_um * 1e-6 / (5 * source_area),
        "plate_base": 0.001 / (180 * source_area),
        "convection": 1 / (h * wetted_effective),
    }
    return dict(channels=channels, chips_per_module=chips_per_module,
                heat_per_chip_w=heat, tim_um=tim_um, nu=nu, re=re,
                speed=speed, h_w_m2k=h, fin_eta=fin_eta,
                effective_wetted_m2=wetted_effective, dp_pa=dp,
                r_k_w=sum(terms.values()), drop_k=heat * sum(terms.values()),
                terms=terms)


def surface(fluid_k: float, resistance: float, absorbed: float, eps: float) -> tuple:
    flux = eps * SIGMA * fluid_k**4 - absorbed
    for _ in range(15):
        ts = fluid_k - resistance * flux
        residual = flux - (eps * SIGMA * ts**4 - absorbed)
        flux -= residual / (1 + 4 * eps * SIGMA * resistance * ts**3)
        if abs(residual) < 1e-10:
            break
    return fluid_k - resistance * flux, flux


def traverse(inlet: float, resistance: float, absorbed: float,
             eps: float, cells: int = 100) -> tuple:
    fluid, total, mean_surface, mean_gap = inlet, 0.0, 0.0, 0.0
    a = AREA / cells
    capacity = MDOT_LOOP / 4 * CP
    for _ in range(cells):
        ts, flux = surface(fluid, resistance, absorbed, eps)
        for _ in range(12):
            mid = fluid - flux * a / (2 * capacity)
            ts, new_flux = surface(mid, resistance, absorbed, eps)
            if abs(new_flux - flux) < 1e-9:
                break
            flux = new_flux
        fluid -= new_flux * a / capacity
        total += new_flux * a
        mean_surface += ts / cells
        mean_gap += (mid - ts) / cells
    return fluid, total, mean_surface, mean_gap


def solve(p: dict, c: dict, absorbed: float, eps: float = 0.85,
          unknown_dp_kpa: float = 0, cells: int = 100) -> dict:
    dp = KNOWN_EXTERNAL_DP + p["dp_pa"] + c["dp_pa"] + unknown_dp_kpa * 1000
    pump = 2 * dp * MDOT_LOOP / RHO / ETA
    # Screening upper allocation: all electrical pump heat enters main loops.
    target = (100_000 + pump) / 8
    lo, hi = 285.0, 470.0
    for _ in range(46):
        inlet = (lo + hi) / 2
        if traverse(inlet, p["r_area"], absorbed, eps, cells)[1] < target:
            lo = inlet
        else:
            hi = inlet
    inlet = (lo + hi) / 2
    outlet, rejected, ts_mean, gap_mean = traverse(inlet, p["r_area"], absorbed, eps, cells)
    # Allocate pump heat ahead of cold plates. It raises their inlet by this
    # amount, and cold plates still heat their coolant by exactly 10 K.
    pump_rise = pump / (2 * MDOT_LOOP * CP)
    junction = inlet - 273.15 + c["drop_k"]
    return dict(panel_tubes=p["tubes"], chip_channels=c["channels"],
                chips_per_module=c["chips_per_module"], heat_per_chip_w=c["heat_per_chip_w"],
                chip_tim_um=c["tim_um"], chip_nu=c["nu"], absorbed_w_m2=absorbed, emissivity=eps,
                panel_r_area=p["r_area"], chip_drop_k=c["drop_k"],
                unknown_dp_kpa=unknown_dp_kpa, known_plus_assumed_dp_kpa=dp / 1000,
                pump_electric_w=pump, main_heat_kw=(100_000 + pump) / 1000,
                remaining_aux_heat_kw=(17_650 - pump) / 1000,
                hot_fluid_c=inlet - 273.15,
                radiator_outlet_c=outlet - 273.15,
                coldplate_inlet_c=outlet - 273.15 + pump_rise,
                surface_mean_c=ts_mean - 273.15,
                mean_fluid_surface_gap_k=gap_mean,
                panel_net_kw=rejected / 1000,
                junction_c=junction, margin_to_95_k=95 - junction)


def absorbed_limit(p: dict, c: dict, junction_limit: float = 95) -> float:
    lo, hi = -200.0, 400.0
    dp = KNOWN_EXTERNAL_DP + p["dp_pa"] + c["dp_pa"]
    pump = 2 * dp * MDOT_LOOP / RHO / ETA
    target = (100_000 + pump) / 8
    inlet_limit = junction_limit - c["drop_k"] + 273.15
    for _ in range(35):
        mid = (lo + hi) / 2
        if traverse(inlet_limit, p["r_area"], mid, .85)[1] > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    out = Path(__file__).resolve().parent
    panels = [panel(n) for n in (12, 20, 32)]
    chips = [chip(n) for n in (120, 160)]
    rows = [solve(p, c, absorbed) for p in panels for c in chips
            for absorbed in (0, 45, 100, 150, 200)]
    rows += [solve(panel(20), chip(), 45, eps=.75),
             solve(panel(32), chip(160), 45, eps=.75),
             solve(panel(20), chip(), 45, unknown_dp_kpa=50),
             solve(panel(20), chip(), 45, unknown_dp_kpa=150),
             solve(panel(20), chip(tim_um=100), 45),
             solve(panel(20), chip(nu=3.61), 45)]
    rows += [solve(panel(n), chip(m, chips_per_module=10), 45)
             for n in (20,32) for m in (120,160)]
    write_csv(out / "thermal_structure_v04.csv", rows)
    write_csv(out / "thermal_panel_structure_v04.csv", panels)
    chip_rows = []
    for c in chips + [chip(n, chips_per_module=10) for n in (120,160)]:
        row = {k: v for k, v in c.items() if k != "terms"}
        row.update({"r_" + k: v for k, v in c["terms"].items()})
        chip_rows.append(row)
    write_csv(out / "thermal_chip_structure_v04.csv", chip_rows)
    for p in panels:
        print(f"panel {p['tubes']} tubes R''={p['r_area']:.5f} "
              f"Re={p['re']:.0f} h={p['h_w_m2k']:.0f} dp={p['dp_pa']/1000:.2f}kPa")
    for c in chips:
        print(f"chip {c['channels']} channels drop={c['drop_k']:.2f}K "
              f"Re={c['re']:.0f} dp={c['dp_pa']/1000:.2f}kPa")
    for row in rows:
        if row["panel_tubes"] == 20 and row["chip_channels"] == 120:
            print(f"q_abs={row['absorbed_w_m2']:.0f} eps={row['emissivity']:.2f} "
                  f"chip_W={row['heat_per_chip_w']:.0f} "
                  f"extra_dp={row['unknown_dp_kpa']:.0f}kPa "
                  f"TIM={row['chip_tim_um']:.0f}um Nu={row['chip_nu']:.2f} "
                  f"Tf_hot={row['hot_fluid_c']:.3f}C Tj={row['junction_c']:.3f}C")
    limits = []
    for p in panels:
        for c in chips:
            limits.append(dict(panel_tubes=p["tubes"], chip_channels=c["channels"],
                               chips_per_module=c["chips_per_module"],
                               max_absorbed_95=absorbed_limit(p, c, 95),
                               max_absorbed_90=absorbed_limit(p, c, 90)))
    write_csv(out / "thermal_limits_v04.csv", limits)
    print("limits", limits)
    cache = out.parent / "work" / "matplotlib-cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(8.5, 5.0), constrained_layout=True)
    colors = ("#b85134", "#226e96", "#408254")
    for p, color in zip(panels, colors):
        for c in chips:
            selected = [r for r in rows[:30] if r["panel_tubes"] == p["tubes"]
                        and r["chip_channels"] == c["channels"]]
            ax.plot([r["absorbed_w_m2"] for r in selected],
                    [r["junction_c"] for r in selected], color=color,
                    linestyle="-" if c["channels"] == 120 else "--", marker="o",
                    label=f"{p['tubes']} tubes/panel, {c['channels']} channels/chip")
    ax.axhline(95, color="#222222", linewidth=1.5, label="95 C junction limit")
    ax.axhline(90, color="#777777", linestyle=":", label="90 C comparison target")
    ax.axvline(45, color="#aaaaaa", linestyle=":")
    ax.set(xlabel="Absorbed external heat per active front area (W/m2)",
           ylabel="Modeled junction temperature (C)",
           title="100 kW computing: geometry-based thermal screening\n20 x 500 W sources per module, 40 x 40 mm each")
    ax.grid(alpha=.2)
    ax.legend(fontsize=8, loc="upper left")
    fig.savefig(out / "thermal_structure_v04.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
