# Decisions de disseny

## 1. Escala de risc cardiovascular: SCORE2 per defecte, REGICOR configurable

**Decisió.** El motor fa servir **SCORE2 / SCORE2-Diabetes** per defecte i **REGICOR** com a
alternativa configurable. Es tria a `config/rules.yaml`:

```yaml
risc_cardiovascular:
  escala: score2        # score2 | regicor | totes_dues
  llindar_risc_alt: 10  # %
```

**Per què SCORE2 per defecte.**
- És l'escala de les guies ESC actuals.
- SCORE2-Diabetes inclou **FGe i HbA1c**, alineada amb el repte cardio-renal-metabòlic.

**Per què REGICOR com a alternativa.**
- És la més implantada a l'atenció primària espanyola; molts centres la tenen integrada a la
  història clínica.

**Conseqüència.** L'escala és una **peça intercanviable del motor**: cada comunitat o centre pot
triar la seva sense tocar codi. El mode opcional `totes_dues` calcula les dues escales durant una
transició. Tall de risc alt: ≥ 10% (pendent de validar pel metge; els talls de les dues escales no
són estrictament equivalents).

## 2. Capa de dades amb connectors

Tota font de dades implementa `connectors.base.Connector` (`get_patients`, `get_patient_data`) i
retorna el model de `model/`. El motor no sap d'on venen les dades. Avui hi ha dos connectors
(FHIR R4 i CSV) sobre els mateixos pacients, i un test garanteix que donen el mateix resultat.
Afegir una font nova (eCAP, DIRAYA...) és afegir un connector.

## 3. Regles a configuració

Llindars i activació de cada regla a `config/rules.yaml` (`enabled: true/false`), perquè el metge
els pugui validar i canviar sense tocar codi.

## 4. FGe amb CKD-EPI 2021

Les dades sintètiques calculen el FGe amb **CKD-EPI 2021** (creatinina, sense coeficient de raça).
**Pendent de confirmar pel metge:** les societats europees de laboratori recomanen mantenir
CKD-EPI 2009 sense factor racial. La fórmula és a `model/formules.py`; canviar-la és un canvi d'una
funció i tornar a executar el generador.

## 5. Dades de referència amb data fixa

Les dades sintètiques tenen una data de referència fixa (13/11/2026) perquè la demo i els tests
siguin reproduïbles. A FHIR viatja al `timestamp` del bundle i el connector la fa servir per
calcular l'edat.
