# Proyecto: CardioAlert AP (Hackathon Boehringer Ingelheim - Reto 1)

## Contexto Clínico
- **Usuario:** Médica de Atención Primaria (Carmen) en el Sistema Nacional de Salud (SNS) español. Consulta con tiempo muy limitado (5-7 min/paciente) y datos fragmentados.
- **Problema:** Pacientes con analíticas aparentemente "aceptables" esconden alto riesgo cardiovascular (RCV) o síndrome cardiorrenal-metabólico incipiente (diabetes, HTA, albuminuria sin valorar, caída silenciosa del Filtrado Glomerular eGFR, signos tempranos de insuficiencia cardíaca).
- **Objetivo:** Herramienta de cribado pasivo, priorización automática y ayuda a la decisión preventiva sin añadir carga administrativa (cero clics extra innecesarios).

## Stack Tecnológico
- **Lenguaje:** Python 3.x
- **Frontend / Demo:** Streamlit (interfaz limpia, estilo historia clínica electrónica moderna del SNS / tipo DIRAYA o eCAP, colores médicos: blanco, azul clínico, alertas en verde/ámbar/rojo).
- **Visualización:** Plotly o Altair para gráficas de evolución temporal (ej. caída de eGFR y subida de albuminuria).
- **Datos:** Dataset sintético local en CSV/JSON (`pacientes_cupo.csv`) con ~30 pacientes realistas de un cupo de Atención Primaria, incluyendo históricos analíticos de los últimos 2 años.

## Lógica Clínica del Algoritmo de Riesgo (Score Cardiorrenal)
El sistema debe cruzar automáticamente variables y tendencias, no solo valores aislados:
1. **Deterioro Renal Silencioso:** eGFR (CKD-EPI) entre 45-60 mL/min o caída >5 mL/min/año + Cociente Albúmina/Creatinina en orina (CAC / UACR) >30 mg/g (albuminuria no valorada previamente).
2. **Riesgo Metabólico/Vascular:** HbA1c en rango prediabético/límite (5.7% - 6.9%) o diabético + PAS >135 mmHg + LDL >115 mg/dL.
3. **Alerta Cardíaca Precoz:** NT-proBNP ligeramente elevado (>125 pg/mL) o combinación de HTA + Diabetes + Albuminuria.
4. **Regla de Oro (Explicabilidad):** Cada paciente priorizado debe mostrar en 1 línea el *porqué* de la alerta y una *acción preventiva sugerida* (ej. "Solicitar CAC en orina", "Valorar inicio de iSGLT2 / nefroprotección", "Citar para cribado IC").

## Instrucciones de Desarrollo para Claude
- Prioriza una interfaz visual impactante, rápida y fácil de demostrar en un pitch de 5 minutos.
- No compliques el backend: todo debe correr en local con datos sintéticos realistas listos para enseñar.
- Genera código modular (`app.py`, `risk_engine.py`, `data_generator.py`).

## Interoperabilidad y Fragmentación del SNS (Valor Diferencial)
- El sistema simula una capa de interoperabilidad basada en el estándar **HL7 FHIR** capaz de agregar y normalizar analíticas dispersas entre distintos silos (Atención Primaria, Laboratorio Hospitalario, Urgencias y distintas Comunidades Autónomas como DIRAYA, eCAP, SERGAS, etc.).
- En `pacientes_cupo.csv` y en la Ficha Clínica, cada registro analítico debe mostrar su **Sistema de Origen** (ej. "eCAP - Cataluña", "DIRAYA - Andalucía", "Lab. Hospitalario") para demostrar visualmente cómo la herramienta une puntos que el médico no vería por separado en sus 6 minutos de consulta.

## Estándar Clínico Oficial: Guías ESC/ERA 2026 (Marco "STAMP on CKD")
- **Cálculo de eGFR:** Usar ecuación CKD-EPI 2009 sin factor racial (calibrada para población europea).
- **Cribado Dual:** Detectar pacientes con HTA, DM2 o ECV a los que les falte medición anual de **uACR** (albuminuria) o que presenten uACR >= 30 mg/g (A2) o > 300 mg/g (A3) no valorada.
- **Estratificación de Riesgo:**
  - Clasificar según matriz **KDIGO** (G1-G5 x A1-A3) y verificar cronicidad (>= 3 meses) vs. caída aguda inesperada (alerta de posible FRA/AKI -> retest en días/semanas).
  - Aplicar penalización de riesgo equivalente al **SCORE2 CKD Add-On** (reclasificación al alza cuando coexisten eGFR reducido y albuminuria).
  - Calcular criterio de derivación a Nefrología (**KFRE > 3-5% a 5 años**, eGFR < 30, uACR >= 700 mg/g o duplicación de uACR).
  - Ajustar interpretación de **NT-proBNP**: < 125 pg/mL descarta IC; >= 500 pg/mL alerta sospecha de IC en ERC avanzada.
- **Sugerencias Terapéuticas (Clase I ESC 2026):**
  - Alertar oportunidad de **iSGLT2** (DM2 + eGFR >= 20, o no-DM2 + eGFR >= 20 + uACR >= 200 mg/g), **Estatina** (si eGFR < 60 sin tratamiento hipolipemiante, sin importar LDL), **IECA/ARA-II** (objetivo PAS 120-129 mmHg), **Finerenona** (DM2 + uACR >= 30 mg/g + K <= 4.8) o **Semaglutida** (DM2 + albuminuria).
  - **Aviso anti-inercia/anti-sobrecarga:** Mostrar nota clínica indicando que una caída inicial de eGFR < 30% tras iniciar iSGLT2/IECA es esperada y no requiere suspender fármaco, y que iSGLT2 no exige analítica extra de control. Alertar si toma AAS en prevención primaria sin ECV (Clase III).
  
---

## Estado actual del repo (actualizado 13/11/2026) — prevalece sobre lo anterior si hay conflicto

### Estructura
```
connectors/   Capa de datos. base.py (interfaz Connector: get_patients, get_patient_data),
              fhir_connector.py y csv_connector.py. Devuelven siempre el modelo de model/.
model/        entitats.py (dataclasses Pacient, Analitica [con `origen`], Diagnostic, Medicacio, DadesPacient),
              cataleg.py (LOINC, CIAP-2/CIE-10, grupos ATC), formules.py (CKD-EPI 2009 y 2021).
config/       rules.yaml: `rules` (las 8 reglas con "enabled", umbrales, "evidencia" y "pes") y `motor`
              (ecuación FGe, fecha de referencia, FRA, derivación, oportunidades terapéuticas, prioridad).
              Todo pendiente de validar por el médico.
engine/       Motor de reglas determinista (ver "Motor de reglas" más abajo).
scripts/      generate_patients.py: generador sintético (seed 42) -> data/synthetic/.
data/synthetic/  fhir/ (un bundle FHIR R4 por paciente) y csv/ (patients, observations, conditions, medications).
tests/        test_connectors.py (FHIR == CSV + 8 casos trampa), test_dades_sintetiques.py (coherencia),
              test_engine.py (fórmulas, 8 casos trampa, controles, cambio de escala, reglas a mano).
docs/         dades_sintetiques.md (criterios de generación), decisions.md (decisiones de diseño).
api/          API — PENDIENTE (vacío).
frontend/     Interfaz — PENDIENTE (vacío).
```

### Comandos
- Requiere Python >= 3.10. Si el `python` del PATH es más antiguo, crear un venv local
  (`py -3.14 -m venv .venv`) y usar `.venv/Scripts/python`.
- `pip install -r requirements.txt`
- `python scripts/generate_patients.py` regenera los datos (determinista; no editar data/synthetic a mano).
- `python -m pytest` ejecuta los tests.
- `python -m engine` resume el cupo priorizado; `python -m engine P003` imprime la nota clínica de un paciente.

### Motor de reglas (`engine/`)
- `risk_engine.py`: `RiskEngine(connector, config=rules.yaml, data_referencia=None)` con `avalua(id)`,
  `avalua_cupo()` (ordenado por prioridad) y `avalua_dades(DadesPacient)`. Devuelve `ResultatPacient`:
  `nivell_risc` (ALT/MITJA/BAIX), `puntuacio_prioritat` (0-100), `categoria_kdigo`, `risc_kdigo`, `estat_renal`,
  `fge_actual`, `uacr_actual`, `pendent_fge`, `kfre_5a`, `risc_cv`, `alertes_actives` (`Alerta`: regla, motiu,
  evidencia "Clase X - ESC/ERA 2026", pes, fonts), `accions_recomanades` (`Accio` con `nota` anti-inercia),
  `avisos`, `ben_tractat`, `objectius_pendents`, `resum` (1 línea), `fonts_dades`, `nota_clinica_auto`.
- `renal.py`: funciones puras — categorías y matriz KDIGO, cronicidad (>= 2 medidas separadas >= 3 meses),
  pendiente del FGe (regresión lineal), caída aguda (FRA) y KFRE de 4 variables.
- `escales.py`: registro `ESCALES` (`score2` = SCORE2 / SCORE2-Diabetes / SCORE2-OP, `regicor`) y
  `ckd_addon` (SCORE2 CKD Add-on). Añadir una escala = añadir una función al registro.
- El motor **recalcula el FGe desde la creatinina** con `motor.equacio_fge` (CKD-EPI 2009 sin factor racial);
  no usa el FGe informado por el laboratorio (que en los datos sintéticos es CKD-EPI 2021).
- Alertas: las 7 reglas de `rules` + `possible_fra`, `derivacio_nefrologia` y `aas_prevencio_primaria`
  (sección `motor`). `ben_tractat` es el control positivo: con RCV alto pero tratamiento y objetivos
  correctos NO se alerta. Las oportunidades terapéuticas (iSGLT2, IECA/ARA-II, estatina, PA, finerenona,
  arGLP-1) generan acciones, no alertas.
- `puntuacio_prioritat` = suma de `pes` de las alertas + peso KDIGO (máx. 100); niveles según `motor.prioritat`.
- Textos de salida (alertas, acciones, nota) en castellano; cero umbrales en el código.
- Coeficientes de SCORE2/SCORE2-OP/SCORE2-Diabetes/CKD Add-on contrastados con el paquete R RiskScorescvd;
  los de REGICOR y KFRE y las clases de evidencia de `rules.yaml` están pendientes de verificar con el médico.

### Decisiones tomadas (detalle en docs/decisions.md)
- **Dataset:** 100 pacientes sintéticos (no ~30 ni `pacientes_cupo.csv`), histórico nov 2022 - nov 2026,
  fecha de referencia fija 13/11/2026. Los 8 casos trampa son P001-P008 (ver docs/dades_sintetiques.md).
- **Escala de riesgo CV:** SCORE2/SCORE2-Diabetes por defecto, REGICOR configurable
  (`risc_cardiovascular.escala: score2 | regicor | totes_dues`). Corte de riesgo alto >= 10%.
  La escala es una pieza intercambiable del motor.
- **FGe:** el motor usa **CKD-EPI 2009 sin factor racial** (configurable en `motor.equacio_fge`). El FGe
  guardado en los datos sintéticos sigue siendo el "informado por el laboratorio" con CKD-EPI 2021; el motor
  lo ignora y recalcula (p. ej. Pilar López: 52 informado -> 49 con la 2009).
- **Origen de los datos:** cada `Analitica` lleva `origen` (columna `origen` en CSV, `Observation.performer`
  en FHIR). Por defecto "eCAP - Catalunya"; NT-proBNP "Lab. Hospital"; la analítica de 2025 de José
  Fernández (P003) viene de "DIRAYA - Andalucía" y es la que permite confirmar su albuminuria.
- **Reglas en YAML:** umbrales en config/rules.yaml, nunca hardcodeados en el motor.
- **Conectores:** el motor solo conoce la interfaz `Connector`; añadir una fuente = añadir un conector.
- **Convenciones:** identificadores y docs en catalán; textos clínicos de los datos en castellano.
  Códigos: LOINC (pruebas), CIAP-2 + CIE-10 (diagnósticos), ATC (fármacos, agrupados por prefijo).
- **Git:** commit y push a main tras cada paso que funcione.
