"""Generate the native QGIS view from the acquired WaPOR windows."""
from pathlib import Path

from qgis.core import (
    Qgis, QgsApplication, QgsColorRampShader, QgsCoordinateReferenceSystem, QgsProject,
    QgsRasterLayer, QgsRasterShader, QgsRectangle, QgsReferencedRectangle,
    QgsSingleBandPseudoColorRenderer, QgsVectorLayer,
)
from qgis.PyQt.QtGui import QColor

ROOT = Path(__file__).resolve().parent
RULES = {
    "AETI": [(0, "#f5f2d8"), (350, "#adc89e"), (600, "#4a9b82"), (1000, "#124762"), (2500, "#182342")],
    "GBWP": [(0, "#eef3ed"), (1, "#d4d0ec"), (2, "#9e91cf"), (4, "#5c49a4"), (7, "#31215c")],
}


def build():
    project = QgsProject.instance()
    project.setTitle("WaPOR Water Productivity Atlas | Moulay Bousselham")
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    for indicator, stops in RULES.items():
        for level in ("L1", "L2"):
            path = ROOT / "data" / "raw" / f"WAPOR-3.{level}-{indicator}-A.2023.tif"
            lyr = QgsRasterLayer(str(path), f"{indicator} · {level} · 2023", "gdal")
            if not lyr.isValid() or lyr.crs().authid() != "EPSG:4326":
                raise ValueError(f"QGIS could not load {path.name}")
            provider = lyr.dataProvider()
            scale = provider.bandScale(1)
            if scale not in (0.001, 0.1):
                raise ValueError(f"Unexpected QGIS band scale for {path.name}: {scale}")
            ramp = QgsColorRampShader()
            ramp.setColorRampType(QgsColorRampShader.Interpolated)
            ramp.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), str(v)) for v, c in stops])
            shader = QgsRasterShader(stops[0][0], stops[-1][0])
            shader.setRasterShaderFunction(ramp)
            lyr.setRenderer(QgsSingleBandPseudoColorRenderer(provider, 1, shader))
            project.addMapLayer(lyr)
            project.layerTreeRoot().findLayer(lyr.id()).setItemVisibilityChecked(indicator == "AETI" and level == "L2")
    zones = QgsVectorLayer(str(ROOT / "data/zones.geojson"), "Analysis zones", "ogr")
    if not zones.isValid() or zones.featureCount() != 2:
        raise ValueError("QGIS could not load the two analysis zones")
    symbol = zones.renderer().symbol()
    layer = symbol.symbolLayer(0)
    layer.setFillColor(QColor(0, 0, 0, 0))
    layer.setStrokeColor(QColor("#f2efe3"))
    layer.setStrokeWidth(0.7)
    project.addMapLayer(zones)
    project.viewSettings().setDefaultViewExtent(
        QgsReferencedRectangle(QgsRectangle(-6.322, 34.838, -6.106, 34.956), project.crs()))
    path = ROOT / "atlas.qgs"
    if not project.write(str(path)):
        raise RuntimeError("QGIS failed to write atlas.qgs")
    project.clear()
    if not project.read(str(path)) or len(project.mapLayers()) != 5 or not all(l.isValid() for l in project.mapLayers().values()):
        raise RuntimeError("Saved QGIS project could not be re-opened with all five layers")
    print(f"QGIS {Qgis.QGIS_VERSION}: four rasters and two zone geometries re-opened successfully.", flush=True)
    project.clear()


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        build()
    finally:
        app.exitQgis()
