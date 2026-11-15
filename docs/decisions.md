# Decisions de disseny

> **Estat de validació.** Recomanacions, llindars i classes d'evidència revisats i validats per David Cebotari (metge, equip The GOATS) el 15/11/2026. Els coeficients de les fórmules estan transcrits de les publicacions originals citades. Tests automàtics: SCORE2 es comprova contra l'exemple publicat a l'article (50 anys, fumador/a, PAS 140 mmHg, colesterol total 5,5 i HDL 1,3 mmol/L, regió de risc baix: 5,9 % en home i 4,2 % en dona); CKD-EPI 2009 i REGICOR, contra casos calculats amb la fórmula publicada; SCORE2-OP, SCORE2-Diabetes, CKD Add-on i KFRE només tenen tests propis de coherència (selecció del model, rang i sentit de l'efecte), sense exemple publicat. SCORE2, SCORE2-OP, SCORE2-Diabetes i CKD Add-on es van contrastar, a més, amb el paquet R RiskScorescvd (fora dels tests automàtics).

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
transició. Tall de risc alt: ≥ 10% (validat per David Cebotari (metge de l'equip) el 15/11/2026; els talls de les dues escales no
són estrictament equivalents).

### Actualització 14/11/2026: mode ESC automàtic i talls per edat

La clau passa a ser `escala_per_defecte` (`score2` | `regicor` | `totes_dues`) i el tall únic del 10%
desapareix. L'escala també es pot triar en calent (`RiskEngine(..., escala="regicor")`, selector de la web).

- **`score2` = mode ESC automàtic.** El motor tria la variant per pacient: diabetis i 40-69 anys →
  SCORE2-Diabetes; ≥ 70 anys → SCORE2-OP; < 70 sense diabetis → SCORE2. Menors de 40 anys: no calculable.
- **CKD Add-on** quan hi ha afectació renal (últim FGe < 60 o últim UACR ≥ 30 mg/g; llindars a
  `risc_cardiovascular.ckd_addon`). No s'aplica si l'últim FGe és una caiguda aguda (possible FRA).
- **SCORE2-Diabetes no porta Add-on per defecte** (`ckd_addon.models: [SCORE2, SCORE2-OP]`): l'equació ja
  inclou el FGe i l'Add-on (Matsushita 2023) es va derivar per a SCORE2 i SCORE2-OP; sumar-lo comptaria
  el FGe dos cops. En diabètics amb MRC segueix actuant el mínim per KDIGO (taronja = alt, vermell = molt
  alt). **Validat per david cebotari (metge de l'equip) el 15/11/2026**; es canvia afegint el model a la llista.
- **Talls per edat (ESC)** a `talls_per_edat`: < 50 anys 2,5% / 7,5%; 50-69 anys 5% / 10%; ≥ 70 anys
  7,5% / 15% (risc alt / molt alt). REGICOR té talls propis (`talls_regicor`: 10% / 15%), validats per David Cebotari el 15/11/2026.
- **Sortida per pacient:** `escala_usada`, `risc_cv_percentatge`, `categoria_risc_cv` i `rang_referencia_cv`.
- **Efecte al cupo:** 65 pacients amb risc alt o molt alt (abans 37 alertes amb el tall del 10%) i 55
  alertes de risc CV infratractat. Com que aquesta alerta pesa 30 punts (= llindar del nivell ALT), el
  cupo queda en 58 ALT / 1 MITJA / 41 BAIX. Decisión clínica abierta (siguiente fase): si "risc alt" hauria de pesar
  menys que "risc molt alt" per recuperar un nivell MITJA útil.

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
  paquet R de codi obert RiskScorescvd (CRAN). Els coeficients de REGICOR i de
  KFRE estan transcrits de les publicacions originals: REGICOR té un test amb un cas calculat a mà i KFRE,
  només tests propis de rang i d'ordre (sense exemple publicat). SCORE2 té un test contra l'exemple publicat a
  l'article (`tests/test_referencies_publicades.py`). Les classes de recomanació de
  `rules.yaml` (camp `evidencia`) les ha validat David Cebotari (metge de l'equip) el 15/11/2026.
- **Resolt (14/11/2026):** el tall únic del 10% s'ha substituït pels talls per edat de l'ESC (vegeu la
  secció 1).

## 7. Sistema d'origen de cada analítica

`Analitica.origen` (opcional) indica d'on ve cada registre: columna `origen` al CSV i
`Observation.performer.display` a FHIR. Quan una alerta es basa en dades de més d'un sistema, el motor
ho diu al motiu ("dato cruzado entre DIRAYA - Andalucía y eCAP - Catalunya").

## 8. API, web i edició de paràmetres (14/11/2026)

- **L'API no té lògica clínica.** `api/main.py` només crida el motor i serialitza; rellegeix `rules.yaml`
  a cada petició, de manera que un canvi de llindars es veu a l'instant. La web tampoc calcula res: fins i
  tot els llindars que dibuixa la gràfica arriben de l'API.
- **Edició de `rules.yaml` amb llista blanca.** `POST /api/rules` només accepta els paràmetres de
  `api/rules_store.py::EDITABLES` (amb rang i tipus). Abans d'escriure: validació, coherència (tall "alt" <
  tall "molt alt", nivell MITJA < nivell ALT), avaluació de tot el cupo amb la configuració nova i còpia de
  seguretat a `config/backups/`. S'escriu amb ruamel.yaml per conservar els comentaris del fitxer.
- **Volant.** `volant_auto` surt de les accions recomanades que impliquen una petició (analítiques,
  interconsulta a Nefrologia, ECG/ecocardiograma). Si no n'hi ha cap, queda buit i la web ho diu.
- **Acció nova `valorar_sraa`.** Amb els talls per edat apareixia una alerta de risc CV infratractat amb
  "sin IECA/ARA-II" pendent i cap acció associada; ara proposa "Valorar IECA o ARA-II". Validat per david cebotari (metge de l'equip) el 15/11/2026.
- **Gràfica de la fitxa.** FGe i UACR en dos panells amb el mateix eix de temps (mai dues escales en un
  panell: l'alineació seria arbitrària). La línia és neutra; el color i la forma del punt indiquen el
  sistema d'origen, i la dada que ve d'una altra comunitat s'etiqueta sobre la gràfica.

## 9. Servidor FHIR remot

- `https://hapi.fhir.org/baseR4` és públic i compartit: només hi pugem dades sintètiques, etiquetades amb
  `meta.tag` `urn:cardioalert-ap|the-goats-hackathon` i l'etiqueta de seguretat HTEST. Els ids porten
  el prefix `thegoats-` i es pugen amb PUT (tornar a executar l'script actualitza, no duplica).
- El connector remot només demana recursos amb la nostra etiqueta, descarrega un sol cop (4 cerques
  paginades) i ho desa en memòria. Un test comprova que el cupo avaluat és idèntic al local.
- Si el servidor falla, tarda més de 60 s o no té els pacients, l'API torna a les dades locals, la web
  mostra un avís i no es reintenta fins passats 60 s (per no penalitzar cada clic).

## 10. Servei CDS Hooks i estació clínica simulada (14/11/2026)

> L'estació simulada ja no és una pàgina de la web de l'add-on: des del 15/11/2026 és una aplicació a part
> (`simulador/`). Vegeu la secció 13. El que es diu aquí del servei CDS Hooks continua vigent.

- **Servei CDS Hooks.** `GET /cds-services` (discovery) i `POST /cds-services/cardioalert-patient-view`
  (hook `patient-view`), seguint l'especificació HL7 CDS Hooks 2.0. `api/cds_hooks.py` només tradueix el
  `ResultatPacient` del motor a una targeta; el motor no s'ha modificat.
- **Una targeta per pacient.** `summary` d'una línia i de menys de 140 caràcters (nivell + primera alerta +
  "(+N alertas)"; el `resum` del motor és massa llarg per a aquest camp); `indicator` segons el grup de
  l'ordre de la llista (vegeu la secció 11; abans, segons el nivell ALT / MITJA / BAIX, ja eliminat); `detail` en Markdown amb el motiu de cada alerta i
  l'origen de la dada (si l'alerta no porta fonts, les del pacient); `suggestions` amb les accions del
  motor en el mateix ordre (la primera, `isRecommended`) i `selectionBehavior: any`.
- **Suggeriments sense `actions`.** Són informatius: el servei no escriu res a la història clínica.
- **Sempre es retorna targeta**, també per als pacients sense alertes (`info`: "Sin alertas..." o
  "Bien tratado..."), perquè a la demo es vegi el control positiu. En un desplegament real potser convé
  retornar `cards: []` en aquests casos per no generar fatiga d'alertes. Decisión clínica abierta (siguiente fase).
- **Extensió pròpia:** els paràmetres `source` i `scale` a la URL (els mateixos selectors que la resta de
  l'API). `context.patientId` accepta "P003" o "Patient/P003". Errors: 400 si el hook no és `patient-view`
  o falta `patientId`; 404 si el pacient no existeix. No es fa servir `prefetch` ni `fhirServer`.
- **Estació clínica simulada** (`#/estacion`, `frontend/src/components/EstacionView.jsx`). Imita de forma
  genèrica una història clínica d'atenció primària (agenda, dades del pacient, diagnòstics, medicació i
  analítiques agrupades per informe = data + sistema d'origen). No porta el nom ni el disseny de cap
  producte real i mostra sempre l'etiqueta "Simulación – datos sintéticos". Fa de client CDS Hooks: en
  obrir un pacient crida el hook i pinta la targeta al requadre lateral (i deixa veure el JSON intercanviat).
  Els noms "eCAP - Catalunya" o "DIRAYA - Andalucía" només hi apareixen com a sistema d'origen de cada informe.
- **"Informe recuperado de otra comunidad".** L'API retorna `comunitat_habitual` (la comunitat amb més
  analítiques del pacient, entre els orígens "Sistema - Comunitat"); la web etiqueta els informes d'una
  altra comunitat (p. ex. el de DIRAYA de P003). Els orígens sense comunitat ("Lab. Hospital") no s'etiqueten.

## 11. Ajustos segons la guia ESC 2021 de prevenció cardiovascular (14/11/2026)

Font: *2021 ESC Guidelines on cardiovascular disease prevention in clinical practice* (Eur Heart J
2021;42:3227): **taula 5** (categories de risc per edat), **figura 3** (regions de risc) i **figura 6**
(objectius de tractament). Tot el que segueix és a `config/rules.yaml` i està **validat per David Cebotari (metge de l'equip) el 15/11/2026**.

**Calibració (figura 3).** Espanya és un país de **risc baix**. El motor ja feia servir aquesta calibració
(`regio_score2: baix`, per defecte també a `engine/escales.py`) per a SCORE2, SCORE2-Diabetes i SCORE2-OP:
no ha calgut corregir res. Ara hi ha un test que ho fixa.

**Àmbit d'aplicació de SCORE2 / SCORE2-OP (persones "aparentment sanes").**

| Cas | Com es tracta |
|---|---|
| Malaltia CV establerta (`diagnostics_ecv`) | "Muy alto" directe, sense escala (ja era així) |
| Diabetis, 40-69 anys | SCORE2-Diabetes (ja era així). **Nou:** si falta HbA1c o creatinina ja no es fa servir SCORE2 com a substitut: "Faltan datos para calcular el riesgo" |
| Diabetis, ≥ 70 anys | SCORE2-OP, que porta la diabetis com a variable (SCORE2-Diabetes només està validada fins als 69 anys) |
| Afectació renal (FGe < 60 o UACR ≥ 30) | SCORE2 / SCORE2-OP **+ CKD Add-on** i, amb MRC confirmada, categoria mínima segons KDIGO (taronja = alt, vermell = molt alt), que coincideix amb la MRC moderada / greu de la guia. Mai SCORE2 "pelat" |
| Hipercolesterolèmia familiar | **Nou:** `diagnostics_hf` → "Alto" directe, sense escala. La llista és **buida**: el catàleg no té cap codi d'HF i no n'inventem cap; cal que el metge digui quin codi fa servir |
| Menors de 40 anys | **Nou:** "Escala SCORE2 no aplicable (<40 años)" (`edat_min: 40`). Només s'avaluen les regles renals i les proves pendents (no `possible_ic`, ni risc CV, ni AAS) |

**Classificació (taula 5).** L'únic nivell de risc que es mostra és la categoria de la taula 5:
"Bajo-moderado", "Alto" o "Muy alto", amb el % i el rang de referència de l'edat. Les etiquetes
ALT / MITJA / BAIX s'han eliminat del motor (`nivell_risc` ja no existeix), de l'API, de la targeta CDS
Hooks, de l'Excel i de la web. Camps nous: `text_risc_cv` (la categoria o el motiu pel qual no n'hi ha),
`estat_risc_cv`, `regicor_referencia` i `nota_calibracio`.

**Ordre de la llista de treball (no és una classificació).** `grup_ordre` / `grup_ordre_text`:
1. alertes clíniques urgents (`motor.prioritat.alertes_urgents`: `possible_ic`, `possible_fra`,
   `derivacio_nefrologia`); 2. risc "Muy alto" sense tractament adequat; 3. risc "Alto" sense tractament
adequat; 4. la resta. Dins de cada grup, per la puntuació del motor. "Sense tractament adequat" vol dir
que té l'alerta `risc_cardiovascular`, és a dir, algun objectiu pendent. El bloc "Hoy: N pacientes
prioritarios" són els N primers (`motor.prioritat.pacients_avui`, 10). A la targeta CDS, `indicator` surt
del grup (1 = `critical`, 2 i 3 = `warning`, 4 = `info`), perquè l'especificació demana una urgència visual.

**Textos i punts de l'alerta.** Segons la categoria (`risc_cardiovascular.alertes`): "Alto" → "Riesgo
cardiovascular alto: valorar tratamiento (decisión compartida)" (20 punts); "Muy alto" → "Riesgo
cardiovascular muy alto: tratamiento generalmente recomendado" (35 punts); ≥ 70 anys aparentment sans →
"Valorar tratamiento considerando fragilidad, polimedicación y preferencias del paciente (clase IIb)" (els
punts de la seva categoria). Els punts de totes les alertes es poden editar a la pantalla de paràmetres;
es valida que "Muy alto" sumi més que "Alto". L'alerta cita "ESC 2021" (`risc_cardiovascular.guia`); les
classes I / IIa / IIb que hi consten són les de les recomanacions de la guia i s'han de verificar.

**Avís de calibració.** El mode per defecte és `totes_dues`: es calculen l'escala ESC i REGICOR. La
categoria surt **sempre** de SCORE2 / SCORE2-OP / SCORE2-Diabetes; REGICOR no reclassifica mai i es
mostra al costat amb la nota "Las escalas europeas pueden sobreestimar el riesgo en población española.
REGICOR (calibrada para población catalana): X %". REGICOR només es calcula entre 35 i 74 anys. El selector
"Calculadora CV" de la web s'ha tret; `escala="regicor"` segueix existint al motor i a l'API només per
fer comparacions manuals (no és la taula 5).

**Objectius de tractament (figura 6), esglaonats.** `ben_tractat.pressio_objectiu` i `ldl_objectiu`.
- **Pas 1 = criteri de "ben tractat" (si no s'assoleix, hi ha alerta):** PAS < 140 mmHg i LDL < 100 mg/dL.
  L'objectiu propi dels diabètics (130/80) s'ha eliminat.
- **Pas 2 = acció d'intensificació (no alerta):** PAS < 130 "si se tolera" i LDL < 70 (risc alt) o < 55
  (risc molt alt), "según tolerancia y preferencias".
- **Per què esglaonat:** aplicar LDL < 55 com a criteri d'alerta faria saltar el control positiu P007
  (Francisco Jiménez, LDL 68 amb estatina i risc molt alt), que ha de continuar sense alertes. Ara P007
  no té cap alerta i rep una acció opcional d'intensificació. **Decisió validada per David Cebotari (metge de l'equip) el 15/11/2026.**

**Dades que falten.** Sense PAS, colesterol total o HDL: "Faltan datos para calcular el riesgo" i la
prova que falta surt com a acció recomanada (i al volant).

**Efecte a la cohort demo (100 pacients, sense tocar-los).** Categories: 35 "Bajo-moderado", 31 "Alto",
34 "Muy alto" (cap menor de 40 ni amb dades que faltin). Ordre de la llista: 8 alertes urgents, 26 "Muy
alto" sense tractament adequat, 25 "Alto" sense tractament adequat i 41 a la resta. 59 alertes de risc CV
(30 "muy alto", 21 "alto" i 8 amb el text de ≥ 70 anys); 77 pacients amb REGICOR de referència. Els 8
casos trampa es continuen detectant i P007 i P008 continuen sense alertes.

## 12. Cohort realista i selector de cohort (14/11/2026)

> **Actualització 15/11/2026 (secció 14):** la cohort ja no es tria a la web de l'add-on. Les dues cohorts
> són dades de l'estació clínica simulada (`simulador/datos`), el cupo actiu es tria a l'estació i l'add-on
> el llegeix per FHIR. El paràmetre `cohort` només queda per a `source=local` (tests).

Detall, fonts i taula comparativa a `docs/cohort_realista.md`.

- **Dues cohorts.** "Demo (100)" (`simulador/datos/demo`, intacta: 8 casos trampa i prevalences inflades per a
  la demo) i "Cupo realista (1.500)" (`simulador/datos/realista`), generada amb
  `python scripts/generate_patients.py --perfil realista --n 1500` (llavor fixa) i calibrada amb REGICOR
  (factors de risc) i ENRICA (MRC), estratificat per edat i sexe. Paràmetres a `config/cohort_realista.yaml`.
- **Pacients individuals, no taules.** Cada pacient té el seu historial de 4 anys. Les prevalences
  s'assignen per **quota exacta** dins de cada estrat d'edat i sexe, amb una predisposició latent per
  pacient perquè els factors s'acumulin en els mateixos pacients (com a ENRICA).
- **Taxes per edat abans que el total.** La MRC es genera amb les taxes per edat d'ENRICA; amb una piràmide
  d'edat actual el total surt 17,5% (ENRICA: 15,1%). Decisión clínica abierta (siguiente fase): què es prefereix fixar.
- **"Veritat" del generador** a `simulador/datos/realista/veritat.csv`: permet saber quantes MRC sense diagnosticar
  hi ha de debò (175) i quantes en detecta el motor (129, sense falsos positius).
- **Només local.** La cohort realista no es puja al servidor FHIR públic: l'script de pujada només llegeix
  `simulador/datos/demo` i l'API la llegeix del disc (CSV). Amb `cohort=realista`, la font és sempre local.
- **L'IMC** s'afegeix al catàleg de proves (LOINC 39156-5) només per a aquesta cohort; el motor no el fa servir.
- **API:** paràmetre `cohort=demo|realista` a `/api/cupo`, `/api/pacientes/{id}`, `/api/export/excel` i al
  servei CDS Hooks; `GET /api/cohorts` diu quines hi ha. Si la realista no està generada, es torna a la
  demo amb un avís.
- **Resultats en memòria.** Cada cupo s'avalua un sol cop per combinació de cohort, font i escala, i se'n
  guarden els resultats i el JSON ja serialitzat; la fitxa, l'Excel i la targeta CDS surten del mateix
  càlcul. A cada petició es compara el contingut de `rules.yaml`: si ha canviat, es llença tot i es
  recalcula (per això un canvi de paràmetres es continua veient a l'instant). Amb 1.500 pacients: uns 0,6 s
  la primera petició i uns 0,05 s les següents; la resposta va comprimida (gzip).
- **Web:** selector "Cohorte" a la capçalera (també `?cohort=realista` a la URL). En canviar de cohort es
  torna a la llista, perquè els pacients d'una no existeixen a l'altra. La llista es pinta de 100 en 100 i
  l'agenda de l'estació clínica mostra els 150 primers (la resta, amb el cercador).
- **Limitacions conegudes:** no hi ha malaltia CV establerta ni hipercolesterolèmia familiar a les dades;
  el seguiment i el tractament són supòsits de l'equip; les xifres dels articles no s'han tornat a
  contrastar amb les taules originals.

## 13. L'add-on i el simulador són dues aplicacions (15/11/2026)

Objectiu: demostrar que CardioAlert AP és un **add-on que s'instal·la** en una estació clínica existent, no
una pantalla més d'una mateixa web. Substitueix la part de l'estació simulada de la secció 10.

- **Dues aplicacions, tres ports.** ADD-ON: API (`api/`, 8000) + interfície (`frontend/`, 5173). SIMULADOR:
  estació clínica (`simulador/`, 5174), amb el seu `package.json`. El simulador no importa res de l'add-on ni
  crida `/api/...`: només `GET /cds-services`, `POST /cds-services/<servei>` i la URL de llançament.
- **L'estació té la seva pròpia història clínica.** Un plugin de Vite (`simulador/servidor-fhir.js`) serveix
  els bundles de `simulador/datos/demo/fhir` com un servidor FHIR de només lectura (`/fhir/Patient`,
  `/fhir/Patient/{id}/$everything`, `/fhir/metadata`). Per això l'estació funciona sencera sense l'add-on, i
  no necessita Python. La "data d'avui" de la simulació és el `timestamp` dels bundles (13/11/2026).
- **Instal·lació per URL.** A "Configuración → Integraciones" hi ha un sol camp (la URL de l'add-on, per
  defecte `http://localhost:8000`). En instal·lar, l'estació fa el discovery i mostra els serveis trobats;
  l'estat es desa a `localStorage` i es manté en recarregar. "Desinstalar" l'esborra. Sense add-on no hi ha
  ni panell ni botó, i la paraula "CardioAlert" no surt enlloc de l'estació.
- **Com sap l'estació on és la interfície de l'add-on?** No ho escriu l'usuari: el discovery l'anuncia al camp
  `extension` del servei (`extension["cardioalert-app"].launchUrl`, que l'especificació CDS Hooks permet), i
  la targeta porta un enllaç `links` de tipus `smart`. L'API la llegeix de `CARDIOALERT_UI_URL`.
- **Finestra modal amb la interfície completa.** El botó de la barra d'eines (i l'enllaç de la targeta) obre
  un iframe amb `launchUrl/?iss=<FHIR de l'estació>&launch=<context>`. És un **llançament SMART on FHIR
  simulat**: en un llançament real, `launch` és un identificador opac que l'aplicació bescanvia per OAuth 2.0
  pel pacient i l'usuari; aquí porta directament aquest context (JSON en base64url: `patient`, `fhirUser`,
  `practitioner`, `ehr`). No hi ha autenticació: només serveix per a la demo amb dades sintètiques.
  La interfície de l'add-on (`frontend/src/launch.js`) s'obre a la fitxa del pacient i mostra una franja amb
  l'estació, el professional, el pacient i els enllaços "Ficha de P003" i "Lista «Hoy» y cupo".
- **Si l'add-on no respon.** Totes les crides tenen límit de temps. L'estació mostra un avís a dalt, el
  panell diu "El add-on no responde" amb "Reintentar", el botó porta l'etiqueta "no responde" i la finestra
  comprova que la interfície contesta abans de pintar l'iframe. La història clínica continua disponible.
- **Scripts.** `start_addon`, `start_simulador` i `start_demo` (.bat i .sh): instal·len dependències si
  falten, comproven versions i ports, i imprimeixen les URL. Els `.bat` fan servir `npm.cmd`.
- **El motor no s'ha tocat.** Cap canvi a `engine/`, `model/`, `connectors/`, `config/` ni a les dades; els
  resultats de les dues cohorts i les tres escales són idèntics byte a byte als d'abans.
- **Què quedava pendent (resolt a la secció 14).** Les dades eren a `data/`, l'add-on i l'estació llegien
  la mateixa carpeta i el simulador només mostrava la cohort demo.

## 14. Les dades són de l'estació: l'add-on les llegeix per FHIR (15/11/2026)

Objectiu: que la demo funcioni com la realitat. Les dades dels pacients són de l'estació clínica; l'add-on
**no té dades pròpies** i les llegeix del servidor FHIR de l'estació, que li arriba per tres estàndards.

```
ESTACIÓ (simulador, 5174)                                   ADD-ON (API 8000 + interfície 5173)
  simulador/datos/<cupo>/fhir   <- les dades són aquí
  servidor FHIR  /fhir   <----------- GET Patient/{id}/$everything ------  targeta CDS i fitxa
                         <----------- GET Group, Group/{id}/$export ------  cupo sencer (Bulk Data, NDJSON)
  obrir un pacient  ---- POST /cds-services/... { fhirServer, context.patientId [, prefetch] } --->
  botó / targeta    ---- iframe  launchUrl/?iss=<servidor FHIR>&launch=<context> ---------------->
```

- **Les dades es mouen al simulador.** `data/synthetic` -> `simulador/datos/demo` i `data/realista` ->
  `simulador/datos/realista` (fhir/, csv/ i veritat.csv). El generador continua a `scripts/` (és una eina de
  desenvolupament), però escriu allà. S'han actualitzat les rutes del generador, l'API, el CLI, els tests,
  `upload_to_fhir.py` i els scripts d'arrencada. Cap fitxer de dades ha canviat de contingut.
- **Servidor FHIR R4 de l'estació** (`simulador/servidor-fhir.js`, sense dependències). Corre dins del
  servidor de l'estació (plugin de Vite, port 5174) i també sol (`node simulador/servidor-fhir.js --port N`,
  que és com el proven els tests). Només lectura i sense autenticació. Rutes: `metadata`, cerca de `Patient`
  (`name`, `_id`, `identifier`, `_count`), `Patient/{id}`, `Patient/{id}/$everything`, `Group` (el cupo actiu)
  i l'exportació.
- **Cupo actiu = recurs Group.** L'estació té dos cupos (`Cupo demo`, 100, i `Cupo realista`, 1.500) i un
  d'actiu, que es tria a "Configuración → Cupo / centro" (`GET /estacion/cupos`, `POST /estacion/cupo`: són
  administració de l'estació, no FHIR). L'estat és del servidor, no del navegador: així el servidor FHIR, la
  història clínica i l'add-on veuen sempre el mateix cupo. `GET /fhir/Group` retorna el Group del cupo actiu
  amb `quantity` i `meta.versionId` (empremta del contingut dels fitxers).
- **FHIR Bulk Data simplificat.** `GET /fhir/Group/{id}/$export` respon `202` amb `Content-Location`;
  l'estat (`/fhir/$export-status/{treball}`) retorna el manifest (`transactionTime`, `output` amb un fitxer
  per tipus) i cada fitxer és NDJSON (`application/fhir+ndjson`). És el flux de l'especificació; el que és
  simplificat és que l'exportació acaba a l'instant, no hi ha OAuth (`requiresAccessToken: false`) ni
  cancel·lació, i el treball no guarda estat (el seu identificador és cupo + versió de les dades).
- **Connector `fhir_ehr`** (`connectors/fhir_ehr_connector.py`). `cupo()` llegeix el Group (una petició
  lleugera), `llegeix_pacient(id)` fa `$everything`, `carrega_cupo()` fa l'exportació Bulk Data (segueix el
  `202`, consulta l'estat fins que acaba, baixa els NDJSON) i deixa el cupo en memòria. Reaprofita la lectura
  de recursos del connector FHIR de fitxers. Només accepta adreces del mateix servidor que la base (no
  segueix un `Content-Location` o un `output.url` que apunti a un altre lloc). L'edat es calcula amb la data
  de les dades de l'estació (`timestamp` / `transactionTime`), igual que fa el connector de fitxers.
- **CDS Hooks.** El servei llegeix el pacient, per aquest ordre: (1) del `prefetch` de la petició, si porta
  les quatre claus que anuncia el discovery (`patient`, `observations`, `conditions`, `medications`);
  (2) del `fhirServer` de la petició (`Patient/{id}/$everything`); (3) de l'estació per defecte. Si no pot
  llegir les dades respon `412 Precondition Failed`, com demana l'especificació. L'estació simulada envia
  `fhirServer` i no resol el prefetch (és opcional per a l'estació): així la demo ensenya la lectura FHIR.
  La targeta ja no depèn del cupo: un sol pacient, una sola petició.
- **Llançament SMART simulat.** L'estació obre la interfície amb `?iss=<servidor FHIR>&launch=<context>`.
  La interfície no llegeix FHIR directament: reenvia l'`iss` a l'API (`/api/cupo?iss=...`,
  `/api/pacientes/{id}?iss=...`, `/api/export/excel?iss=...`). Sense `iss`, l'API fa servir
  `CARDIOALERT_FHIR_URL` (per defecte `http://localhost:5174/fhir`). Continua sense OAuth.
- **Dos botons, dues pantalles.** El context del llançament porta `intent` (paràmetre de context de SMART):
  el botó de la barra d'eines envia `lista-trabajo` i obre la pàgina principal (alertes, "Hoy" i llista de
  prioritats); l'enllaç de la targeta envia `ficha-paciente` i obre la fitxa. En tots dos casos el pacient
  obert viatja com a context i queda a un clic ("Ficha de P003").
- **Memòria per servidor FHIR.** L'API guarda un connector per `iss` amb el cupo exportat i les avaluacions
  fetes amb ell. A cada petició del cupo mira el Group de l'estació (mil·lisegons): si l'empremta
  (`id | quantity | versionId`) ha canviat, torna a exportar i a avaluar. `refresh=true` (botó "Actualizar"
  de la capçalera) ho força. Un canvi a `rules.yaml` torna a avaluar però no torna a llegir l'estació.
  La fitxa llegeix el pacient en viu (`$everything`), sense esperar l'exportació del cupo.
- **Quins servidors FHIR s'accepten.** `fhirServer` i `iss` arriben de fora: l'API només llegeix de les
  adreces que encaixen amb `CARDIOALERT_FHIR_PERMITIDOS` (per defecte, només aquest ordinador) i respon
  `403` a la resta. En un desplegament real serien les estacions registrades, amb el seu token.
- **Si l'estació no respon.** `502` amb un missatge clar (la web el mostra amb "Reintentar"); al hook, `412`.
  No hi ha cap pla B amb fitxers locals: l'add-on no té dades pròpies.
- **Interfície de l'add-on.** Sense selector de cohort ni de font. La capçalera diu, només com a informació,
  "Datos de: Estación clínica simulada – Cupo realista (1.500)" (el nom surt del `CapabilityStatement` i del
  Group) i l'adreça del servidor FHIR.
- **Altres fonts.** Els connectors `csv`, `fhir` (fitxers) i `fhir_remote` (HAPI) es mantenen per als tests
  i com a exemple: `source=local|remote` i `cohort=demo|realista` a l'API, i
  `create_app(font_per_defecte="local")` als tests antics. No són el camí de la demo ni surten a la web.
  `python -m engine` llegeix els fitxers de la cohort demo; amb `--ehr` llegeix de l'estació.
- **Resultats idèntics.** El motor, les fórmules, els llindars i `rules.yaml` no s'han tocat. Llegint de
  l'estació (Bulk Data i `$everything`), els resultats de les dues cohorts i les tres escales són idèntics
  byte a byte als d'abans del canvi (`tests/test_fhir_ehr.py` ho comprova amb una estació simulada i amb el
  servidor Node real).
- **Temps (portàtil de desenvolupament, 15/11/2026).** Cupo realista des de l'estació: uns 1,6 s a l'API
  (1,1 s d'exportació Bulk Data i lectura de 32 MB de NDJSON, 0,3 s de motor, la resta serialització) i uns
  2 s al navegador des del clic fins a la llista pintada. Després, 0,04 s (memòria). Cupo demo: 0,1 s.
  Fitxa i targeta CDS: menys de 10 ms.
- **Límits.** Sense OAuth ni `fhirAuthorization` (simulació). L'estació no resol el prefetch. El cupo es
  demana sencer (sense `_since`): amb cupos molt més grans caldria exportació incremental. El servidor FHIR
  del simulador guarda l'índex en memòria: si es regeneren les dades cal reiniciar l'estació.

## 15. Finestra de dades: minimització (art. 5.1.c RGPD) (15/11/2026)

Principi: el RGPD (art. 5.1.c, "minimització de dades") demana que les dades siguin "adequades, pertinents i
limitades al que és necessari" per a la finalitat. L'add-on no necessita tota la història del pacient per
avaluar les regles: només els últims anys de cada prova que fan servir les regles que la consulten.

- **On es configura.** `motor.finestra_dades` de `config/rules.yaml`: per a cada prova del catàleg
  (`model/cataleg.py`), els `anys` enrere des de la data de referència i les `regles` que la necessiten.
  `anys: 0` vol dir que el motor no la fa servir. Les proves que no són a la llista tampoc s'hi fan servir.
  `enabled: false` desactiva la finestra (com abans). Validat per david cebotari (metge de l'equip) el 15/11/2026.
- **On s'aplica.** `RiskEngine.minimitza(d)` filtra les analítiques abans de qualsevol regla
  (`avalua_dades`) i de la gràfica (`series_renals`). La fitxa de l'API (`/api/pacientes/{id}`) també
  retorna només aquestes dades, i la interfície ho explica a la taula "Analíticas que usa el motor".
  Diagnòstics i tractaments no tenen finestra: són problemes crònics i tractaments actius, que les regles
  necessiten sigui quina sigui la data en què es van registrar.
- **Finestres triades** (les mínimes, en anys sencers, que no canvien cap resultat de les dues cohorts; ho
  comprova `tests/test_finestra.py` comparant amb la finestra desactivada):

  | Prova | Anys | Regles | Per què |
  |---|---|---|---|
  | Creatinina (FGe recalculat) | 5 | fge_descens, mrc_no_diagnosticada, possible_fra, derivacio_nefrologia, creatinina_falta, risc CV | pendent anual del FGe amb tota la sèrie; amb 4 anys canvien 1 + 26 pacients |
  | UACR | 5 | mrc_no_diagnosticada, albuminuria_sense_accio, derivacio_nefrologia, uacr_falta, risc CV | cronicitat i duplicació; amb 4 anys en canvia 1 |
  | NT-proBNP | 4 | possible_ic | amb 3 anys canvien 3 + 11 pacients (NT-proBNP antics que disparen l'alerta) |
  | PAS, PAD, colesterol total, HDL, LDL, potassi | 3 | risc CV, ben_tractat, finerenona | només l'últim valor; amb 2 anys canvien 48 pacients del cupo realista |
  | HbA1c | 2 | risc CV (SCORE2-Diabetes), ben_tractat | només l'últim valor dels diabètics |
  | FGe informat, glucosa, triglicèrids, IMC | 0 | cap | el motor no les fa servir (el FGe es recalcula de la creatinina) |

- **Coherència.** La finestra de la UACR i de la creatinina cobreix el termini màxim sense prova de
  `uacr_falta` i `creatinina_falta` (12 mesos, editable fins a 60): si no, l'alerta diria "sin ninguna
  determinación" en lloc de "hace N meses". El test ho comprova.
- **Decisión clínica abierta (siguiente fase).** Una NT-proBNP de fa 4 anys continua disparant `possible_ic` perquè la regla
  validada fa servir l'últim valor; clínicament potser caldria una finestra més curta (p. ex. 1-2 anys) i
  demanar-ne una de nova. No s'ha canviat perquè alteraria resultats ja validats.
- **Límit.** La finestra s'aplica dins de l'add-on, després de llegir l'estació. El pas següent seria
  demanar-li només aquestes dates (`Patient/{id}/$everything?start=` o `_typeFilter` a l'exportació Bulk
  Data), perquè les dades antigues ni tan sols surtin de l'estació. El servidor del simulador encara no ho
  admet.

## 16. Estat de les alertes, «Hoy», proves pendents i recàlcul (15/11/2026)

- **«Hoy» a dalt de la pàgina principal.** Els N primers de la llista de treball (`motor.prioritat.pacients_avui`,
  editable a la Vista 3) que estan pendents i tenen alguna alerta que compta. `fge_descens` passa a
  `alertes_urgents` (validat pel metge): P002 i P004 pugen al grup 1. Grups de la cohort demo: 10 / 26 / 24 / 40
  (abans 8 / 26 / 25 / 41); realista: 42 / 216 / 325 / 917 (abans 28 / 224 / 331 / 917). Cap alerta,
  categoria de risc, valor de risc ni KDIGO ha canviat: només el grup i la puntuació.
- **Estat de l'alerta per pacient.** "Pendiente" (sense registre), "Citado", "Revisado" i "Pospuesto hasta
  <data>". Els tres últims surten de «Hoy» però continuen al cupo (filtre «Estado» de la llista). És l'única
  cosa que desa l'add-on: `api/estats.py` escriu `estat_addon/<servidor>/estats.json` (escriptura atòmica) i
  `auditoria.jsonl` (només s'hi afegeix), **separat per servidor FHIR**, que simula l'emmagatzematge dins de la
  infraestructura de Salut. No són dades clíniques de l'estació sinó el que el professional ha fet amb cada alerta.
- **Qui fa el canvi.** El professional del context de llançament (`launch.practitioner` i `fhirUser`). Sense
  llançament la interfície no deixa canviar l'estat i l'API respon 422 si no arriba el professional: un canvi
  sense autor no es pot auditar. En producció vindria del token SMART, no del cos de la petició.
- **Alerta nova -> "Pendiente".** Cada registre guarda les alertes que tenia el pacient en canviar l'estat. Si
  un recàlcul (cupo, fitxa o `recalcular`) en porta una que no hi era, l'estat torna a "Pendiente" i el log
  ho registra amb "CardioAlert AP (recálculo automático)" com a autor i la regla nova com a motiu. Una
  posposició arriba a la data (de referència del motor) i torna a comptar com a pendent sense esborrar-se.
- **Proves pendents.** `uacr_falta` i `creatinina_falta` (`motor.prioritat.alertes_fora_avui`) continuen sent
  alertes, però no sumen punts, no fan entrar ningú a «Hoy» ni tornen un pacient a "Pendiente" i no
  encapçalen el resum si n'hi ha una altra. Es resolen de cop des de la vista «Pruebas pendientes»
  (prova, última determinació i des de quan), que s'exporta com a petició conjunta en CSV o Excel.
- **Recàlcul.** La capçalera mostra l'hora de l'últim càlcul del cupo. `POST /api/pacientes/{id}/recalcular`
  torna a llegir el pacient (`$everything`), el substitueix al cupo en memòria de totes les escales d'aquest
  servidor (la llista es reordena) sense tornar a exportar el cupo, i retorna les alertes noves i resoltes.
  Simula l'arribada d'una analítica nova: en producció ho dispararia una notificació de l'estació (p. ex. una
  subscripció FHIR). Les dades del simulador són fixes, de manera que a la demo el recàlcul dona el mateix
  resultat; el test ho prova afegint un NT-proBNP a l'estació simulada.
- **Targeta CDS.** El `summary` l'encapçala `alerta_principal` (la urgent, si n'hi ha), com el resum i la
  llista; abans era la primera alerta de la llista i amb `fge_descens` urgent la targeta sortia "critical"
  amb un títol no urgent.

## 17. Política d'actualització: com s'assabenta l'add-on de la informació nova (15/11/2026)

**Problema.** L'add-on no té dades pròpies: quan a l'estació entra una analítica o un pacient nou, se n'ha
d'assabentar sense que la metgessa hagi d'obrir el pacient ("l'eina vigila per la metgessa").

**Decisió: quatre mecanismes, tots estàndard, de més ample a més fi.**

| Mecanisme | Quan | Què llegeix | Estàndard |
|---|---|---|---|
| Exportació del cupo sencer | Cada nit (en producció) i a la demo en obrir l'add-on, amb «Actualizar» o si canvia el `Group` | Tot el cupo | FHIR Bulk Data (`Group/{id}/$export`) |
| Temps real en obrir un pacient | Cada cop que la metgessa obre la història (targeta) o la fitxa | Aquell pacient | CDS Hooks `patient-view` + `Patient/{id}/$everything` |
| Recàlcul per esdeveniment | Quan arriba una dada nova a l'estació | Aquell pacient | FHIR Subscriptions (R4 Backport IG) |
| Finestra de dades per prova | Sempre | Només els anys que fa servir cada regla | Minimització (§15) |

A la realitat, l'esdeveniment també pot arribar del motor d'integració del laboratori (missatges HL7 v2
ORU^R01) o, a Catalunya, de la plataforma d'esdeveniments de Salut; per a l'add-on és el mateix: "dada nova del
pacient X" -> recalcular X.

**1. Actualitzar en cada lectura.** La fitxa (`/api/pacientes/{id}`) i la targeta CDS llegeixen el pacient de
l'estació i ara també en substitueixen el resultat al cupo en memòria (`substitueix` a `api/main.py`): la fitxa i
la llista «Hoy» sempre coincideixen. Si el resultat no ha canviat, no es toca res (llegir una fitxa no costa
res al cupo).

**2. Escriptura a l'estació (simulador).** El servidor FHIR del simulador accepta `POST /fhir/Observation` i
`POST /fhir/Patient`. El que s'hi escriu viu en memòria (els fitxers de `simulador/datos` no es toquen: els
genera el script i són deterministes; en reiniciar l'estació es perd). La data de l'analítica la posa
l'estació: és el "hoy" de la simulació (13/11/2026, la data de referència del motor), perquè els càlculs de
pendents i de caiguda aguda del FGe siguin coherents. Cada escriptura dona `meta.versionId` al recurs i canvia la
versió del `Group`. A la història hi ha "Registrar analítica" (prova LOINC, valor, unitat i sistema d'origen) i a
l'agenda, "Alta de paciente".

**3. FHIR Subscriptions (R4 Backport IG, simplificat).**
- El discovery de CDS Hooks anuncia, a `extension["cardioalert-app"].subscription`, la subscripció que vol
  l'add-on: tema "Observation nueva de un paciente del cupo", canal `rest-hook`, endpoint `/api/notificaciones`,
  contingut `id-only`. En instal·lar l'add-on, l'estació crea la `Subscription` al seu servidor FHIR; en
  desinstal·lar-lo, la borra. Si l'estació s'ha reiniciat (les subscripcions viuen en memòria), la torna a crear
  en obrir-se.
- Quan entra una Observation, l'estació fa POST d'un Bundle `history` amb el `SubscriptionStatus` (Parameters:
  `events-since-subscription-start`, `notification-event` amb `event-number`, `focus` =
  `Observation/{id}/_history/{versionId}` i `additional-context` = el Patient i el `Group/{id}/_history/{versió}`).
- L'add-on recalcula NOMÉS aquell pacient (`CuaRecalculs`): espera 1 s (`CARDIOALERT_RETARD_NOTIFICACIONES`) i
  cada notificació del mateix pacient torna a posar el rellotge, de manera que diverses analítiques seguides
  donen un sol recàlcul. Si apareix una alerta NOVA, el pacient torna a "Pendiente" i entra a «Hoy» (la regla de
  §16); si les alertes són les mateixes, l'estat no canvia.
- Idempotència: la clau és el `focus` amb la versió del recurs; una notificació repetida es registra però no es
  recalcula.
- La versió del `Group` que porta la notificació queda "incorporada": la propera lectura del cupo no el torna a
  exportar. Si es perd un esdeveniment (salt a `event-number`), el cupo es torna a exportar sencer a la petició
  següent. Un pacient nou no genera notificació (el tema és Observation): canvia el `Group` (`quantity`) i entra
  a la propera lectura.
- Seguretat: només s'accepten notificacions de les estacions de `CARDIOALERT_FHIR_PERMITIDOS` (l'URL de la
  Subscription). Sense OAuth ni handshake (simulació).
- La interfície de l'add-on fa un poll lleuger de `/api/estados` cada 4 s: si `versio_cupo` ha canviat, torna a
  demanar el cupo (i la fitxa oberta) sense spinner i mostra "Datos nuevos de la estación clínica". La targeta del
  simulador es torna a demanar en registrar una analítica o en tornar a obrir el pacient.

**4. Registre d'activitat (AuditEvent).** A més del log de canvis d'estat (§16), cada acció queda a
`estat_addon/<servidor>/activitat.jsonl` com a recurs FHIR **AuditEvent**: `agent` (qui: el professional del
context de llançament, que la interfície envia a cada petició com a `launch`, o "CardioAlert AP (automático)";
a les crides CDS Hooks, el `userId`, i se'n mostra el nom si ja es coneix), `recorded` (quan), `entity` (el
pacient i el detall), `subtype` + `action` (quina acció) i `source.site` (des de quina estació). Accions:
consulta de la fitxa, crida CDS Hooks, notificació rebuda, recàlcul, lectura del cupo (Bulk Data), canvi d'estat,
exportació (Excel del cupo, proves pendents en CSV o Excel) i canvi de paràmetres de rules.yaml. Vista
"Registro de actividad" (`#/actividad`) amb filtres per pacient, professional i tipus d'acció;
`/api/actividad?formato=fhir` retorna el Bundle d'AuditEvent.

**Resultats.** Sense dades noves, el motor dona exactament el mateix que abans (els tests de les dues cohorts no
canvien). Flux provat amb `start_demo.bat`: P005 "Revisado" -> UACR 450 mg/g (DIRAYA - Andalucía) a l'estació ->
en menys d'1 s torna a "Pendiente", 2n de «Hoy», amb "Criterio de derivación a Nefrología: UACR duplicado
(17 → 450 mg/g) [dato cruzado entre eCAP - Catalunya y DIRAYA - Andalucía]", i al registre: notificació,
recàlcul i tornada a "Pendiente"; el cupo no s'ha tornat a exportar.

**Pas futur.** Exportació incremental `Group/{id}/$export?_since=<última exportació>` per al botó «Actualizar» i
per a la càrrega nocturna (avui el cupo s'exporta sencer); handshake i heartbeat de les subscripcions; OAuth
(SMART Backend Services) per a les notificacions i per a Bulk Data.
