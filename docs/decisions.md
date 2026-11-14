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
  alt). **Pendent de validar pel metge**; es canvia afegint el model a la llista.
- **Talls per edat (ESC)** a `talls_per_edat`: < 50 anys 2,5% / 7,5%; 50-69 anys 5% / 10%; ≥ 70 anys
  7,5% / 15% (risc alt / molt alt). REGICOR té talls propis (`talls_regicor`: 10% / 15%), pendents de validar.
- **Sortida per pacient:** `escala_usada`, `risc_cv_percentatge`, `categoria_risc_cv` i `rang_referencia_cv`.
- **Efecte al cupo:** 65 pacients amb risc alt o molt alt (abans 37 alertes amb el tall del 10%) i 55
  alertes de risc CV infratractat. Com que aquesta alerta pesa 30 punts (= llindar del nivell ALT), el
  cupo queda en 58 ALT / 1 MITJA / 41 BAIX. Pendent de decidir amb el metge si "risc alt" hauria de pesar
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
  paquet R de codi obert RiskScorescvd (CRAN). **Pendent de verificar:** coeficients de REGICOR i de
  KFRE (transcrits de les publicacions) i les classes de recomanació de `rules.yaml` (camp `evidencia`).
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
  "sin IECA/ARA-II" pendent i cap acció associada; ara proposa "Valorar IECA o ARA-II". Pendent de validar.
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

- **Servei CDS Hooks.** `GET /cds-services` (discovery) i `POST /cds-services/cardioalert-patient-view`
  (hook `patient-view`), seguint l'especificació HL7 CDS Hooks 2.0. `api/cds_hooks.py` només tradueix el
  `ResultatPacient` del motor a una targeta; el motor no s'ha modificat.
- **Una targeta per pacient.** `summary` d'una línia i de menys de 140 caràcters (nivell + primera alerta +
  "(+N alertas)"; el `resum` del motor és massa llarg per a aquest camp); `indicator` segons el nivell
  (ALT = `critical`, MITJA = `warning`, BAIX = `info`); `detail` en Markdown amb el motiu de cada alerta i
  l'origen de la dada (si l'alerta no porta fonts, les del pacient); `suggestions` amb les accions del
  motor en el mateix ordre (la primera, `isRecommended`) i `selectionBehavior: any`.
- **Suggeriments sense `actions`.** Són informatius: el servei no escriu res a la història clínica.
- **Sempre es retorna targeta**, també per als pacients sense alertes (`info`: "Sin alertas..." o
  "Bien tratado..."), perquè a la demo es vegi el control positiu. En un desplegament real potser convé
  retornar `cards: []` en aquests casos per no generar fatiga d'alertes. Pendent de decidir amb el metge.
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
