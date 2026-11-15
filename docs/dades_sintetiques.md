# Dades sintètiques: criteris de generació

> **Estat: Decisión clínica abierta (siguiente fase).** Tots els valors, proporcions i llindars d'aquest
> document són una proposta de l'equip tècnic. Cap dada correspon a un pacient real.

Generador: `scripts/generate_patients.py` (llavor fixa `seed = 42`, resultat reproduïble).
Sortida: `simulador/datos/demo/fhir/` (un bundle FHIR R4 per pacient) i `simulador/datos/demo/csv/`.

## Població

- 100 pacients, 40-85 anys, 50% homes, noms espanyols. IDs `P001`-`P100`.
- Data de referència ("avui" de la demo): **13/11/2026**. Històric: novembre 2022 - novembre 2026.

| Condició | Proporció al dataset | Nota |
|---|---|---|
| HTA | 40% | |
| Dislipèmia | 43% | |
| Fumadors | 24% | |
| DM2 | 30% | **Inflada a propòsit per a la demo**; la real és ~14% |
| MRC | 20% | Més probable en DM2/HTA |
| IC | 5% | |
| Sense factors de risc | 25% | Ni diagnòstics ni tabac |

Referència real: cohort REGICOR (De Gano et al., *Int J Epidemiol* 2025, doi 10.1093/ije/dyaf116).

## Seguiment

- Crònics (DM2, HTA, MRC, IC o dislipèmia): analítica completa cada 6-12 mesos.
- Sans (i fumadors sense altres diagnòstics): cada 2-3 anys.
- UACR anual en DM2, HTA i MRC.
- ~25% dels crònics tenen alguna prova que falta: o bé l'UACR fa més de 12 mesos (o no s'ha fet mai),
  o bé fa més de 12 mesos de l'última analítica (creatinina).

## Proves (LOINC i unitats)

| Prova | LOINC | Unitat |
|---|---|---|
| Creatinina | 2160-0 | mg/dL |
| FGe (CKD-EPI 2021) | 62238-1 | mL/min/1,73m² |
| UACR | 9318-7 | mg/g |
| HbA1c | 4548-4 | % |
| Glucosa | 1558-6 | mg/dL |
| Colesterol total | 2093-3 | mg/dL |
| LDL | 13457-7 | mg/dL |
| HDL | 2085-9 | mg/dL |
| Triglicèrids | 2571-8 | mg/dL |
| Potassi | 2823-3 | mmol/L |
| NT-proBNP | 33762-6 | pg/mL |
| Pressió sistòlica | 8480-6 | mmHg |
| Pressió diastòlica | 8462-4 | mmHg |

## Sistema d'origen

Cada analítica porta el sistema d'origen (`origen`): per defecte "eCAP - Catalunya"; l'NT-proBNP,
"Lab. Hospital". L'analítica del 15/04/2025 de José Fernández (primer UACR alterat, 45 mg/g) ve de
"DIRAYA - Andalucía": sense aquesta dada l'albuminúria no quedaria confirmada.

## Coherència clínica

- **El FGe no es genera: es calcula** amb CKD-EPI 2021 a partir de la creatinina (2 decimals), l'edat
  en la data de la prova i el sexe. Els tests ho recalculen per a totes les analítiques.
- Colesterol total = LDL + HDL + TG/5 (Friedewald).
- Diabètics: en tractament o amb HbA1c ≥ 6,5%. No diabètics: HbA1c sempre < 6,5%.
- Glucosa dels diabètics derivada de l'HbA1c (glucosa mitjana estimada) amb soroll.
- **Cap fàrmac sense un diagnòstic que el justifiqui:**

| Grup (ATC) | Diagnòstic que el justifica |
|---|---|
| Metformina (A10BA02), aGLP-1 (A10BJ), insulina (A10A) | DM2 |
| iSGLT2 (A10BK) | DM2, MRC o IC |
| IECA (C09A), ARA-II (C09C) | HTA, MRC o IC |
| Tiazides (C03A), antagonistes del calci (C08C) | HTA |
| Estatines (C10AA) | Dislipèmia |
| Finerenona (C03DA05) | MRC (només es genera en DM2 + MRC) |

- Variabilitat entre mesures: creatinina ±5-10%, UACR ±20-30%, pressió ±10 mmHg.
- Descens del FGe: fisiològic (0,5-1 mL/min/1,73m² per any) en pacients sense MRC; 1-3,5 per any
  en MRC, i 5,5-7 per any en un ~15% dels pacients amb MRC G3 (progressors ràpids).
- MRC: ~70% per filtrat (FGe basal 34-57) i ~30% per albuminúria amb filtrat conservat (UACR ≥ 45).
- Pacients sense MRC: UACR basal < 20 mg/g i FGe basal ≥ 70. NT-proBNP elevat només en IC.

## Diagnòstics (CIAP-2 / CIE-10)

DM2 T90/E11 · HTA K86/I10 · MRC U99.01/N18 · IC K77/I50 · dislipèmia T93/E78 · tabac P17/F17.

## Casos trampa

Fixats a mà (sense soroll), IDs `P001`-`P008`. Cada un està pensat per a una regla del motor.

| # | Pacient | Perfil | Què ha de detectar l'eina |
|---|---|---|---|
| 1 | Antonio García, 64, H | DM2 fa 8 anys, HbA1c 6,8-7,0%, pressió correcta, metformina. Últim UACR: nov. 2023 | `uacr_falta` |
| 2 | Rosa Martínez, 71, D | HTA (enalapril). FGe 85→78→71→64 (2023-2026), creatinina 0,76→0,95 ("normal") | `fge_descens` |
| 3 | José Fernández, 58, H | DM2+HTA, UACR 45 (2025, DIRAYA) i 52 (2026, eCAP), només metformina | `albuminuria_sense_accio` |
| 4 | Pilar López, 67, D | HTA (amlodipí). FGe 55 i 52 separats 6 mesos, UACR 40, sense diagnòstic de MRC | `mrc_no_diagnosticada` |
| 5 | Manuel Sánchez, 62, H | Fumador, HTA+DM2+dislipèmia, 138/88, HbA1c 6,9%, LDL 125; sense estatina, IECA ni iSGLT2 | `risc_cardiovascular` |
| 6 | Dolores Ruiz, 74, D | HTA+DM2, NT-proBNP 450, sense diagnòstic d'IC | `possible_ic` |
| 7 | Francisco Jiménez, 63, H | Mateix perfil que el 5, amb estatina, IECA i iSGLT2 i objectius assolits | Control: `ben_tractat` |
| 8 | Laura Moreno, 45, D | Sana, analítiques normals | Control: cap alerta |

## Preguntes obertes per al metge

1. Són realistes els valors i les trajectòries dels casos trampa?
2. Resolt: el motor fa servir CKD-EPI 2009 sense factor racial (vegeu `docs/decisions.md`).
3. Les justificacions fàrmac-diagnòstic són massa estrictes? (p. ex. estatina en DM2 sense dislipèmia)
4. Els llindars de `config/rules.yaml` són correctes?
