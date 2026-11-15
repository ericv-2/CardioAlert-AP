# Cohort realista: fonts, objectius i resultat

> **Estat: pendent de validar pel metge.** Són **pacients sintètics**: cap dada correspon a una persona
> real. Les xifres epidemiològiques d'aquest document són les que l'equip ha facilitat a partir dels dos
> articles citats; **no s'han tornat a contrastar amb les taules originals** i cal fer-ho abans de
> presentar-les. Tot el que no surt d'aquests articles està marcat com a **supòsit**.

## Què és

Un cupo d'atenció primària de **1.500 adults** (≥ 18 anys), generat pacient a pacient, cadascun amb el
seu historial de 4 anys (novembre 2022 - novembre 2026): diagnòstics, tractament i analítiques amb el
sistema d'origen. Serveix per veure què faria el motor en un cupo amb prevalences reals, no en els 100
pacients de la demo (que tenen la diabetis i la MRC inflades a propòsit i 8 casos trampa).

```
python scripts/generate_patients.py --perfil realista --n 1500
```

- Llavor fixa (`llavor: 2026` a `config/cohort_realista.yaml`): el resultat és sempre el mateix.
- Sortida a `simulador/datos/realista/`: `fhir/` (un bundle FHIR R4 per pacient), `csv/` i `veritat.csv` (el que el
  generador "sap" de cada pacient: MRC real, tipus, si està diagnosticada, IC...). Identificadors `R0001`-`R1500`.
- **Només en local.** No es puja al servidor FHIR públic: `scripts/upload_to_fhir.py` només llegeix
  `simulador/datos/demo`. `source=local&cohort=realista` (només per a tests) la llegeix del disc.
- Opcions: `--n` (mida del cupo), `--mrc-sense-dx` (part de les MRC sense diagnòstic, per defecte 2/3),
  `--prevalenca-ic` (%), `--llavor`, `--sortida`. La resta de paràmetres, a `config/cohort_realista.yaml`.
- A la demo: les dades són de l'estació clínica simulada. A "Configuración → Cupo / centro" de l'estació
  es tria "Cupo realista" i l'add-on el llegeix del servidor FHIR de l'estació amb Bulk Data (decisions.md
  §14). La interfície de l'add-on ja no té selector de cohort.

## Fonts: quina xifra surt d'on

**REGICOR** — De Gano et al., *Int J Epidemiol* 2025, doi [10.1093/ije/dyaf116](https://doi.org/10.1093/ije/dyaf116).

| Xifra | Origen |
|---|---|
| 35-54 anys: diabetis 7,4%, HTA 21,2%, hipercolesterolèmia 32%, fumadors actuals 32,3% | Taula 1, enquesta 2005 (n = 2.850) |
| Global: diabetis 14%, HTA 40%, hipercolesterolèmia 43%, fumadors 24%, IMC mitjà 27,2 | Xifres globals de la cohort |
| Sans de 35-54 anys: LDL 130 mg/dL, HDL 55 mg/dL, colesterol total 202 mg/dL, glucosa 93 mg/dL, pressió 110/74 mmHg, IMC 25,8 | Taula 1, enquesta 2018 |

**ENRICA** — Gorostidi et al., *Nefrología* 2018, doi [10.1016/j.nefro.2018.04.004](https://doi.org/10.1016/j.nefro.2018.04.004).

| Xifra | Origen |
|---|---|
| MRC global 15,1% | Prevalença global de l'estudi |
| MRC per edat: 4,8% (18-44), 17,4% (45-64), 37,3% (≥ 65) | Prevalença per grups d'edat |
| MRC per sexe: 23,1% homes, 7,3% dones | Prevalença per sexe |
| MRC 4,5% amb 0-1 factors de risc i fins al 52,3% amb 8-10 | Prevalença segons el nombre de factors de risc |

**Supòsits de l'equip tècnic** (cap dels dos articles en dona la xifra; tots editables a la configuració):

| Supòsit | Valor |
|---|---|
| Estructura d'edat i sexe dels adults | Aproximació de la població espanyola actual (padró de l'INE): 22% de 18-34, 36% de 35-54, 17% de 55-64, 25% de ≥ 65 anys; més dones entre els grans |
| Prevalença dels factors fora de 35-54 anys | Triada perquè augmenti amb l'edat i el total s'acosti a les xifres globals (taula de sota) |
| Raó home/dona dels factors | Diabetis i tabac 1,3; HTA 1,1; hipercolesterolèmia 1,0 |
| Part de les MRC sense diagnòstic registrat | 2/3 (el que s'ha demanat per defecte) |
| Tipus i estadi de la MRC | Per filtrat o per albuminúria segons l'edat; G3a 68%, G3b 23%, G4 8%, G5 1% |
| Insuficiència cardíaca | 2% global, concentrada en ≥ 65 anys; 25% sense diagnòstic |
| Seguiment | Qui té analítiques i cada quant, a qui es demana l'UACR (60% dels diabètics i 35% dels hipertensos cada any), 20% dels crònics amb l'última analítica de fa més d'un any |
| Tractament | 55% dels dislipèmics amb estatina, 68% dels hipertensos amb IECA/ARA-II, 22% dels diabètics amb iSGLT2... |
| Altres | 3% de pacients amb una analítica d'una altra comunitat, 0,4% amb una caiguda aguda del FGe, 5% d'AAS en prevenció primària |

No hi ha **malaltia cardiovascular establerta** (infart, ictus): el catàleg de diagnòstics no en té i no
s'ha afegit. En un cupo real, aquests pacients serien "Muy alto" sense escala.

## Com es genera

1. **Edat i sexe** segons l'estructura de la població adulta (no uniforme).
2. **Factors de risc**, per estrat d'edat i sexe i amb **quota exacta**: a cada estrat se li assigna el
   nombre de pacients que toca i s'escullen els de més puntuació. La puntuació combina una
   **predisposició latent** pròpia de cada pacient (la mateixa per a tots els factors) i l'edat, de manera
   que els factors **s'acumulen en els mateixos pacients** en lloc de repartir-se a l'atzar.
3. **IMC**: 25,8 de mitjana en els sans de 35-54 anys i més alt amb diabetis, HTA i dislipèmia, ajustat
   perquè la mitjana global sigui 27,2.
4. **MRC** amb les taxes per edat d'ENRICA i la raó homes/dones de l'estudi (23,1 / 7,3 = 3,16); dins de
   cada estrat és més probable com més factors acumula el pacient. Dos terços queden **sense diagnòstic
   registrat** (més sovint les lleus).
5. **Historial**: visites, tractament coherent amb els diagnòstics i analítiques. El FGe es genera amb
   CKD-EPI 2009 (la del motor); els sans de 35-54 anys queden centrats a la taula 1 de REGICOR.

## Prevalences objectiu per grup d'edat (`config/cohort_realista.yaml`)

| Edat | Pes | Diabetis | HTA | Hipercolesterolèmia | Fumadors |
|---|---|---|---|---|---|
| 18-34 | 22,0% | 1,0 | 3,0 | 12,0 | 27,0 |
| 35-44 | 16,5% | 3,5 | 12,0 | 24,0 | 33,0 |
| 45-54 | 19,5% | 10,7 | 29,0 | 38,8 | 31,7 |
| 55-64 | 17,0% | 19,0 | 58,0 | 62,0 | 24,0 |
| 65-74 | 12,5% | 28,0 | 78,0 | 72,0 | 13,0 |
| ≥ 75 | 12,5% | 34,0 | 90,0 | 74,0 | 6,0 |

Els grups 35-44 i 45-54 estan triats perquè el conjunt 35-54 doni exactament les xifres de la taula 1.

## Resultat: objectiu i obtingut (1.500 pacients, llavor 2026)

| Indicador | Objectiu | Obtingut | n del grup |
|---|---|---|---|
| Diabetis, 35-54 anys (%) | 7,4 | 7,4 | 540 |
| HTA, 35-54 anys (%) | 21,2 | 21,1 | 540 |
| Hipercolesterolèmia, 35-54 anys (%) | 32,0 | 31,9 | 540 |
| Fumadors actuals, 35-54 anys (%) | 32,3 | 32,4 | 540 |
| Diabetis, tota la cohort (%) | 14,0 | 13,9 | 1.500 |
| HTA, tota la cohort (%) | 40,0 | 39,1 | 1.500 |
| Hipercolesterolèmia, tota la cohort (%) | 43,0 | 42,9 | 1.500 |
| Fumadors actuals, tota la cohort (%) | 24,0 | 24,0 | 1.500 |
| IMC mitjà, tota la cohort | 27,2 | 27,2 | 1.500 |
| MRC, 18-44 anys (%) | 4,8 | 4,8 | 578 |
| MRC, 45-64 anys (%) | 17,4 | 17,4 | 547 |
| MRC, ≥ 65 anys (%) | 37,3 | 37,3 | 375 |
| MRC, homes (%) | 23,1 | **26,5** | 724 |
| MRC, dones (%) | 7,3 | **9,1** | 776 |
| MRC, tota la cohort (%) | 15,1 | **17,5** | 1.500 |
| MRC amb 0-1 factors de risc (%) | 4,5 | 6,2 | 857 |
| MRC amb 4-5 factors de risc (%) | 52,3 (amb 8-10 factors) | 57,9 | 126 |
| MRC sense diagnòstic registrat (% de les MRC) | 66,7 | 66,5 | 263 |
| Insuficiència cardíaca (%) | 2,0 | 2,0 | 1.500 |

Valors de l'última analítica dels **sans de 35-54 anys** (291 pacients, 223 amb analítica):

| Prova | Objectiu | Obtingut |
|---|---|---|
| LDL (mg/dL) | 130 | 131,8 |
| HDL (mg/dL) | 55 | 55,3 |
| Colesterol total (mg/dL) | 202 | 204,4 |
| Glucosa (mg/dL) | 93 | 92,8 |
| Pressió sistòlica (mmHg) | 110 | 109,5 |
| Pressió diastòlica (mmHg) | 74 | 72,8 |
| IMC | 25,8 | 25,6 |

### On no quadra, i per què

- **MRC global 17,5% en lloc de 15,1% (i 26,5% / 9,1% per sexe en lloc de 23,1% / 7,3%).** Les taxes
  **per edat** són exactament les d'ENRICA; el total surt d'aplicar-les a l'estructura d'edat de la
  cohort, que és la de la població actual (25% de ≥ 65 anys) i és més envellida que la mostra de
  l'estudi. Amb aquestes taxes i aquesta estructura, el total esperat és 17,5%. No es poden complir
  alhora les taxes per edat, el total i una piràmide d'edat actual; hem prioritzat les taxes per edat.
  La **raó homes/dones** (2,9) sí que és a prop de la de l'estudi (3,2). Si el metge prefereix fixar el
  15,1% global, cal rebaixar les taxes per edat (×0,86) o fer servir una piràmide més jove.
- **MRC segons el nombre de factors.** ENRICA compta fins a 10 factors; aquí n'hi ha 5 (HTA, diabetis,
  dislipèmia, tabac i obesitat), o sigui que "4-5 factors" és el nostre equivalent de "molts". El gradient
  hi és (2,9% → 9,4% → 20,3% → 38,4% → 52,8% → 85,0% amb 0 a 5 factors), però els dos extrems no es poden
  clavar alhora amb un total de MRC més alt que el de l'estudi.
- **HTA global 39,1% en lloc de 40%**: arrodoniment de les quotes per estrat.

## Què comproven els tests (`tests/test_cohort_realista.py`)

Marges amplis a propòsit (amb 1.500 pacients, un grup de 300 té un error de mostreig de ±2-3 punts):
factors de risc a 35-54 anys i globals ±2 punts; IMC mitjà ±0,3; MRC per edat ±2 punts; MRC global igual
al total esperat ±0,5 i entre 14,1% i 19,1%; raó homes/dones de MRC ±20%; MRC amb 0-1 factors ±3 punts i
amb 4-5 factors ±12; MRC sense diagnòstic ±2 punts; IC ±0,3; valors dels sans de 35-54 anys (LDL ±6,
colesterol ±7, la resta ±3, IMC ±0,7). També: que la prevalença augmenti amb l'edat, que els factors
coincideixin en els mateixos pacients més que per atzar, que cada historial sigui coherent (cap fàrmac
sense diagnòstic que el justifiqui), que la generació sigui reproduïble, que FHIR i CSV donin el mateix
i que el motor no doni cap fals positiu de MRC.

## Què fa el motor amb aquesta cohort (14/11/2026)

Càlcul: 0,2 s per avaluar els 1.500 pacients (0,15 ms per pacient) i 0,2 s per llegir els CSV. Per l'API,
la primera petició triga uns 0,6 s (lectura, avaluació i JSON) i les següents uns 0,05 s, perquè el
resultat es guarda en memòria.

| Categoria ESC 2021 (taula 5) | Pacients | % del cupo |
|---|---|---|
| Bajo-moderado | 406 | 27,1% |
| Alto | 340 | 22,7% |
| Muy alto | 246 | 16,4% |
| Escala SCORE2 no aplicable (<40 años) | 456 | 30,4% |
| Faltan datos para calcular el riesgo | 52 | 3,5% |

Dels 992 pacients amb categoria: 40,9% "Bajo-moderado", 34,3% "Alto" i 24,8% "Muy alto".

| Ordre de la llista de treball | Pacients |
|---|---|
| 1. Alertes clíniques urgents | 28 |
| 2. "Muy alto" sense tractament adequat | 224 |
| 3. "Alto" sense tractament adequat | 331 |
| 4. Resta | 917 |

| Alerta | Nombre |
|---|---|
| Risc CV alt o molt alt sense tractament adequat | 579 (263 "alto", 204 "muy alto", 112 amb el text de ≥ 70 anys) |
| UACR pendent | 394 |
| Creatinina pendent | 176 |
| MRC no diagnosticada | 129 |
| AAS en prevenció primària | 24 |
| Pèrdua ràpida de FGe | 22 |
| Criteri de derivació a Nefrologia | 18 |
| Albuminúria sense nefroprotecció | 17 |
| Possible insuficiència cardíaca | 6 |
| Caiguda aguda del FGe (possible FRA) | 5 |
| **Total** | **1.370** (734 pacients amb alguna alerta) |

**MRC sense diagnosticar.** N'hi ha 175 de reals (de 263 MRC). El motor en detecta **129** (74%) amb
l'alerta "ERC no diagnosticada", sense cap fals positiu. De les 46 restants: 18 no tenen cap UACR però
reben l'alerta "UACR pendiente" (diabètics o hipertensos); 10 tenen una sola mesura alterada i queden
"pendents de confirmar"; 13 tenen albuminúria però ningú els ha demanat mai un UACR ni tenen cap
diagnòstic que l'exigeixi (invisibles amb les dades que hi ha); 4 no tenen cap analítica i 1 té l'última
mesura normal.

**Si es mirés REGICOR en lloc de l'escala ESC** (només informatiu; la categoria no canvia mai): dels 773
pacients comparables, 431 quedarien igual, **341 baixarien** de categoria (277 d'"Alto" a
"Bajo-moderado", 33 de "Muy alto" a "Bajo-moderado" i 31 de "Muy alto" a "Alto") i 1 pujaria. No són
comparables 188 pacients de ≥ 75 anys (REGICOR arriba fins als 74), 31 amb la categoria fixada per la
MRC, ni els 508 que no tenen categoria.
Compte: REGICOR mesura risc coronari i fa servir uns altres talls (10% / 15%, pendents de validar), o
sigui que la comparació és orientativa.
