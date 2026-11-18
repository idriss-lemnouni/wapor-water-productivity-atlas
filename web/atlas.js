const filters = document.querySelector("form");
const status = document.querySelector("#status");
const legend = document.querySelector("#legend");
const details = document.querySelector("#details");
const colors = ["#d3eac0", "#9dd0a5", "#69ac88", "#2c826e", "#15564e"];
const ticks = { AETI: [300, 500, 700, 900], GBWP: [1, 2, 3, 4] };
const measure = { AETI: "mm/year", GBWP: "kg/m³" };
const map = window.L ? L.map("map", { scrollWheelZoom: false }).setView([34.891, -6.21], 12) : null;
let zones;
let request;
if (map) {
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);
}

function item(tag, value) {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
}

function showValue(value, unit) {
  return value == null ? "Unavailable" : `${new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(value)} ${unit}`;
}

function showLegend(indicator) {
  const edges = ticks[indicator];
  const bins = [`< ${edges[0]}`, ...edges.slice(1).map((v, i) => `${edges[i]}–<${v}`), `≥ ${edges.at(-1)}`];
  legend.replaceChildren(item("strong", `Area-weighted mean · ${measure[indicator]}`));
  bins.forEach((bin, i) => {
    const entry = item("span", bin);
    const swatch = document.createElement("i");
    swatch.style.backgroundColor = colors[i];
    entry.prepend(swatch);
    legend.append(entry);
  });
}

function showDetails({ properties: p }) {
  const article = item("article", "");
  const values = item("dl", "");
  for (const [label, reading] of [
    ["Area-weighted mean", showValue(p.weighted, p.unit)],
    ["Cell-centre mean", showValue(p.cell_center, p.unit)],
    ["Centroid pixel", showValue(p.centroid, p.unit)],
    ["Valid area", `${(100 * p.coverage).toFixed(1)}%`],
    ["Zone area", showValue(p.area_km2, "km²")],
  ]) {
    values.append(item("dt", label), item("dd", reading));
  }
  article.append(item("h2", p.name), values);
  return article;
}

async function update() {
  request?.abort();
  request = new AbortController();
  const active = request;
  const query = new URLSearchParams();
  for (const field of filters.querySelectorAll("select")) query.set(field.id, field.value);
  const indicator = query.get("indicator");
  status.textContent = "Loading zones…";
  try {
    const response = await fetch(`/api/zones?${query}`, { signal: active.signal });
    if (!response.ok) throw new Error("The atlas data could not be loaded.");
    const layer = await response.json();
    if (active !== request) return;
    details.replaceChildren(...layer.features.map(showDetails));
    showLegend(indicator);
    if (map) {
      const initial = !zones;
      zones?.remove();
      zones = L.geoJSON(layer, {
        style: ({ properties: p }) => ({
          color: "#144b49", weight: 2, fillOpacity: 0.78,
          fillColor: p.weighted == null ? "#9ca39d" : colors[ticks[indicator].filter(t => p.weighted >= t).length],
        }),
        onEachFeature: ({ properties: p }, area) => area.bindTooltip(item("span", p.name)),
      }).addTo(map);
      if (initial && layer.features.length) map.fitBounds(zones.getBounds(), { padding: [28, 28] });
    }
    status.textContent = map ? `${layer.features.length} analysis zones · WaPOR v3` : "Map library unavailable. Zonal estimates are shown below.";
  } catch (error) {
    if (error.name === "AbortError" || active !== request) return;
    details.replaceChildren();
    legend.replaceChildren();
    zones?.remove();
    zones = null;
    status.textContent = error.message;
  }
}

filters.addEventListener("change", update);
update();
