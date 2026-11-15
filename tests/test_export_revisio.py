"""El full de revisió clínica es genera a partir de rules.yaml i porta els valors reals."""
import openpyxl

from engine.export_revisio import exporta_revisio


def test_full_revisio(tmp_path):
    cami = exporta_revisio(tmp_path / "revision.xlsx")
    llibre = openpyxl.load_workbook(cami)
    assert llibre.sheetnames == ["Instrucciones", "Prioritarios", "Revisión"]
    complet = [[c.value for c in fila] for fila in llibre["Revisión"].iter_rows(min_row=2)]
    assert len(complet) > 25
    assert all(f[7] in {"Alta", "Media", "Baja"} for f in complet)
    assert all(not f[9] for f in complet)  # "Fuente exacta" queda en blanc
    assert any("500 pg/mL" in str(f[3]) for f in complet)  # el valor ve de rules.yaml
    prioritaris = [[c.value for c in fila] for fila in llibre["Prioritarios"].iter_rows(min_row=2)]
    assert prioritaris and all(f[7] == "Baja" for f in prioritaris)
