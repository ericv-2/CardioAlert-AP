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

## 4. FGe: el motor fa servir CKD-EPI 2009 sense factor racial

**Decisió (13/11/2026).** El motor recalcula el FGe a partir de la creatinina amb **CKD-EPI 2009 sense
factor racial**, la recomanada a Europa (la 2021 sobreestima el filtrat en població europea). Es tria
a `motor.equacio_fge` de `config/rules.yaml` (`ckd_epi_2009` | `ckd_epi_2021`).

Les dades sintètiques conserven el FGe "informat pel laboratori" amb CKD-EPI 2021 (els casos trampa
estan definits amb aquests valors). El motor no el fa servir: així el resultat no depèn de quina
equació aplica cada sistema d'origen. Conseqüència visible: els FGe del motor són uns 3-5 punts més
baixos que els de l'analítica (Pilar López: 52 informat, 49 amb la 2009).

## 5. Dades de referència amb data fixa

Les dades sintètiques tenen una data de referència fixa (13/11/2026) perquè la demo i els tests
siguin reproduïbles. A FHIR viatja al `timestamp` del bundle i el connector la fa servir per
calcular l'edat.

## 6. Motor de regles determinista

- Sense IA generativa en cap càlcul: fórmules publicades + llindars de `config/rules.yaml`.
  Cada alerta porta la regla, les dades que la disparen, el sistema d'origen i la classe de recomanació.
- **Nivell de risc = prioritat d'actuació**, no risc intrínsec: un pacient amb risc CV alt però ben
  tractat (cas 7) surt BAIX amb `ben_tractat = true`; el risc es mostra igualment a `risc_cv`.
- **Alertes vs. accions.** Les alertes sumen prioritat; les oportunitats terapèutiques (iSGLT2, IECA/ARA-II,
  estatina, pressió, finerenona, arGLP-1) només afegeixen accions recomanades.
- **Cronicitat.** MRC = FGe < 60 o UACR >= 30 en >= 2 mesures separades >= 3 mesos. Una caiguda del
  FGe >= 30% respecte de la mesura anterior és "possible FRA" (retest en 1-2 setmanes); entre el 10% i
  el 30% just després d'iniciar iSGLT2/IECA/ARA-II es marca com a esperada.
- **Risc CV i MRC.** Amb MRC s'aplica el SCORE2 CKD Add-on (FGe + UACR) a SCORE2 i SCORE2-OP
  (SCORE2-Diabetes ja inclou el FGe) i, a més, un mínim per KDIGO: taronja = risc alt, vermell = molt alt.
- **Verificació de coeficients.** SCORE2, SCORE2-OP, SCORE2-Diabetes i CKD Add-on contrastats amb el
  paquet R de codi obert RiskScorescvd (CRAN). **Pendent de verificar:** coeficients de REGICOR i de
  KFRE (transcrits de les publicacions) i les classes de recomanació de `rules.yaml` (camp `evidencia`).
- **Pendent de decidir amb el metge:** el tall únic del 10% marca com a risc alt gairebé tots els majors
  de 70 anys amb SCORE2-OP (37 alertes de risc CV sobre 100 pacients). L'ESC fa servir talls per edat
  (7,5% / 10% / 15%).

## 7. Sistema d'origen de cada analítica

`Analitica.origen` (opcional) indica d'on ve cada registre: columna `origen` al CSV i
`Observation.performer.display` a FHIR. Quan una alerta es basa en dades de més d'un sistema, el motor
ho diu al motiu ("dato cruzado entre DIRAYA - Andalucía y eCAP - Catalunya").
