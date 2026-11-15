"""El full de revisió clínica es genera a partir de rules.yaml i porta els valors reals."""
import openpyxl

from engine.export_revisio import OBERTA, exporta_revisio


def test_full_revisio(tmp_path):
    cami = exporta_revisio(tmp_path / "revision.xlsx")
    llibre = openpyxl.load_workbook(cami)
    assert llibre.sheetnames == ["Instrucciones", "Decisiones abiertas", "Revisión"]
    complet = [[c.value for c in fila] for fila in llibre["Revisión"].iter_rows(min_row=2)]
    assert len(complet) > 25
    assert all(f[7] in {"Validado", OBERTA} for f in complet)
    assert not any("sin verificar" in str(f[8]) or "?" in str(f[8]) for f in complet if f[7] == "Validado")
    assert all(not f[9] for f in complet)  # "Fuente exacta" queda en blanc
    assert any("500 pg/mL" in str(f[3]) for f in complet)  # el valor ve de rules.yaml
    # Les úniques files obertes són les decisions clíniques de la fase següent
    obertes = [[c.value for c in fila] for fila in llibre["Decisiones abiertas"].iter_rows(min_row=2)]
    assert [f[1] for f in obertes] == [f[1] for f in complet if f[7] == OBERTA] and len(obertes) == 4
    assert any("NT-proBNP" in f[1] for f in obertes) and any("hipercolesterolemia" in f[1] for f in obertes)
