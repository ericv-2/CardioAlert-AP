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
  