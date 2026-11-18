"""Produce publication figures from the acquired WaPOR windows and zonal audit."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from zonal import FROM_AREA, ROOT, load_zones

INK = "#1a3e42"
COLORS = {"lagoon-edge": "#932e69", "inland-plain": "#146b57"}
UNITS = {"AETI": "mm/year", "GBWP": "kg/m³"}
ATTRIBUTION = "Data FAO WaPOR v3 · 2022–23 annual layers · CC BY 4.0 · nominal grids L1 300 m and L2 100 m"


def canvas(title, note=ATTRIBUTION, bottom=0.23):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.subplots_adjust(top=0.76, bottom=bottom, left=0.09, right=0.96, wspace=0.30)
    fig.set_facecolor("#fcfdfb")
    fig.text(0.045, 0.92, title, fontsize=17, weight="bold", color=INK)
    fig.text(0.045, 0.045, note, fontsize=9, color="#465e5f")
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    return fig, axes


def render(out):
    out.mkdir(parents=True, exist_ok=True)
    records = json.loads((ROOT / "runs/zonal-results.json").read_bytes())
    zones = load_zones()
    lookup = {(r["zone"], r["year"], r["level"], r["indicator"]): r for r in records}

    fig, axes = canvas("Annual evapotranspiration around Moulay Bousselham",
                       "Data FAO WaPOR v3, 2023 AETI · CC BY 4.0 · same colour scale, units and map extent", bottom=0.17)
    fig.subplots_adjust(right=0.85, wspace=0.26)
    for ax, level in zip(axes, ("L1", "L2")):
        with rasterio.open(ROOT / "data/raw" / f"WAPOR-3.{level}-AETI-A.2023.tif") as ds:
            extent = (ds.bounds.left, ds.bounds.right, ds.bounds.bottom, ds.bounds.top)
            palette = plt.get_cmap("viridis").with_extremes(bad="#e1eaee")
            im = ax.imshow(ds.read(1, masked=True) * ds.scales[0], extent=extent, origin="upper",
                           cmap=palette, vmin=100, vmax=1050, interpolation="nearest")
        for key, (_, polygon) in zones.items():
            x, y = FROM_AREA.transform(*polygon.exterior.xy)
            ax.plot(x, y, lw=1.9, color="white", solid_joinstyle="round")
            ax.plot(x, y, lw=0.85, color=COLORS[key], solid_joinstyle="round")
        ax.set_title(f"{level} · {'300' if level == 'L1' else '100'} m nominal", loc="left", color=INK)
        ax.set(xlim=(-6.315, -6.112), ylim=(34.845, 34.949), xlabel="Longitude")
        ax.set_aspect(1 / np.cos(np.deg2rad(34.9)))
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("Latitude")
    bar = fig.colorbar(im, cax=fig.add_axes([0.885, 0.26, 0.015, 0.40]), extend="both")
    bar.set_label("mm/year", fontsize=9)
    fig.savefig(out / "aeti-grid-comparison.png", dpi=175)
    plt.close(fig)

    fig, axes = canvas("Zonal estimates on the two native grids")
    positions = np.arange(4)
    for indicator, ax in zip(UNITS, axes):
        for i, level in enumerate(("L1", "L2")):
            values = [lookup[key, year, level, indicator]["weighted"] for year in (2022, 2023) for key in zones]
            ax.bar(positions + (i - .5) * 0.34, values, width=.31, label=level, color=("#8da8b7", "#157c69")[i])
        ax.set_xticks(positions, ["Lagoon\n2022", "Plain\n2022", "Lagoon\n2023", "Plain\n2023"])
        ax.set_title(f"{indicator} · {UNITS[indicator]}", loc="left", color=INK)
        ax.legend(frameon=False, ncol=2, loc="upper left", bbox_to_anchor=(0, 1.01))
        ax.set_ylim(0, ax.get_ylim()[1] * 1.17)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.24)
    fig.savefig(out / "zonal-weighted-estimates.png", dpi=175)
    plt.close(fig)

    fig, axes = canvas("A centroid can miss the surrounding zonal pattern",
                       "Values are differences from the area-weighted estimate · data FAO WaPOR v3 · CC BY 4.0", bottom=0.28)
    keys = [(z, y, l) for z in zones for y in (2022, 2023) for l in ("L1", "L2")]
    for indicator, ax in zip(UNITS, axes):
        values = [lookup[zone, year, level, indicator] for zone, year, level in keys]
        for i, method in enumerate(("cell_center", "centroid")):
            difference = [row[method] - row["weighted"] if row[method] is not None else float("nan") for row in values]
            ax.scatter(np.arange(len(keys)) + (i - .5) * .18, difference, s=45, label=("Cell centres", "Centroid")[i],
                       color=("#206e79", "#a84e63")[i], marker=("o", "D")[i])
        ax.axhline(0, color=INK, lw=.85)
        ax.set_xticks(range(len(keys)), [f"{'Lagoon' if z == 'lagoon-edge' else 'Plain'} {y} {l}" for z, y, l in keys],
                      rotation=38, ha="right", fontsize=8)
        ax.set_title(f"{indicator} · {UNITS[indicator]}", loc="left", color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=2, loc="upper right", bbox_to_anchor=(0.96, 0.88))
    fig.savefig(out / "zonal-method-differences.png", dpi=175)
    plt.close(fig)


if __name__ == "__main__":
    render(ROOT / "figures/results")
