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

## Estado actual del repo (actualizado 15/11/2026) — prevalece sobre lo anterior si hay conflicto

### Dos aplicaciones: el ADD-ON y el SIMULADOR
- **ADD-ON (el producto, CardioAlert AP):** motor (`engine/`), API (`api/`, puerto 8000, con el servicio CDS
  Hooks) y su interfaz completa (`frontend/`, puerto 5173: lista "Hoy", cupo, ficha, parámetros).
  **NO tiene datos propios:** los lee del servidor FHIR de la estación clínica (conector `fhir_ehr`).
- **SIMULADOR (`simulador/`, puerto 5174):** la estación clínica de una comunidad, una aplicación web aparte
  con su propia historia clínica. **Los datos de los pacientes son suyos** (`simulador/datos`, las dos
  cohortes) y los sirve su servidor FHIR (`/fhir`). Por defecto NO tiene el add-on: se instala por URL en
  "Configuración → Integraciones". Solo habla con el add-on por estándares (CDS Hooks, lanzamiento SMART on
  FHIR simulado y FHIR Bulk Data); no importa código del add-on ni llama a `/api/...`.

### Flujo de datos (docs/decisions.md §14) — los datos son de la estación, como en la realidad
- **CDS Hooks `fhirServer`:** al abrir un paciente, la estación envía el hook `patient-view` con `fhirServer`
  (su servidor FHIR). El add-on lee el paciente de ahí (`Patient/{id}/$everything`) o del `prefetch` si la
  petición lo trae completo (el discovery anuncia las plantillas); si no puede leer, responde 412.
- **SMART `iss`:** la estación abre la interfaz del add-on con `?iss=<su servidor FHIR>&launch=<contexto>`
  (paciente, profesional e `intent`). La interfaz reenvía el `iss` a la API (`/api/cupo?iss=`,
  `/api/pacientes/{id}?iss=`, `/api/export/excel?iss=`). Sin `iss`: `CARDIOALERT_FHIR_URL`
  (http://localhost:5174/fhir). Lanzamiento SIMULADO, sin OAuth.
- **Bulk Data:** el cupo completo se lee con `GET {iss}/Group` (cupo activo) y `Group/{id}/$export`
  (202 + `Content-Location` -> manifiesto -> NDJSON por tipo de recurso). Simplificado: termina al instante,
  sin OAuth ni cancelación.
- **Memoria por servidor FHIR:** la API guarda el cupo exportado y evaluado de cada `iss`; lo vuelve a leer si
  la estación cambia de cupo o de datos (lo ve en el `Group`: id, `quantity`, `meta.versionId`) o con
  `refresh=true` (botón "Actualizar" de la cabecera). Un cambio en `rules.yaml` reevalúa sin releer.
- **Cupo activo:** en la estación, "Configuración → Cupo / centro" (demo de 100 o realista de 1.500). Es
  estado del servidor de la estación (`GET /estacion/cupos`, `POST /estacion/cupo`), no del navegador.
- **Dos botones:** el botón "CardioAlert AP" de la barra de herramientas abre la PÁGINA PRINCIPAL del add-on
  (`intent: "lista-trabajo"`); el enlace de la tarjeta, la FICHA del paciente (`intent: "ficha-paciente"`).
- **Cabecera del add-on:** sin selector de cohorte ni de fuente; solo informa "Datos de: Estación clínica
  simulada – Cupo realista (1.500)". Si la estación no responde: 502 con mensaje y "Reintentar" (no hay plan B
  con ficheros). Solo se leen servidores FHIR de `CARDIOALERT_FHIR_PERMITIDOS` (por defecto, este ordenador).
- **Otras fuentes (NO son el camino de la demo):** `source=local|remote` y `cohort=demo|realista` en la API,
  solo para tests y como ejemplo; los tests antiguos usan `create_app(font_per_defecte="local")`.
- **Tiempos medidos (15/11/2026):** cupo realista desde la estación ~1,6 s en la API (1,1 s de Bulk Data,
  32 MB de NDJSON) y ~2 s en el navegador; después 0,04 s (memoria). Demo 0,1 s. Ficha y tarjeta < 10 ms.

### Estructura
```
connectors/   Capa de datos. base.py (interfaz Connector: get_patients, get_patient_data),
              fhir_ehr_connector.py (EL DE LA DEMO: servidor FHIR de la estación; Group, $everything, Bulk Data
              y prefetch de CDS Hooks), y, para tests y como ejemplo de otras fuentes, fhir_connector.py
              (ficheros), csv_connector.py y fhir_remote_connector.py (HAPI público, solo recursos con nuestra
              etiqueta). Devuelven siempre el modelo de model/.
model/        entitats.py (dataclasses Pacient, Analitica [con `origen`], Diagnostic, Medicacio, DadesPacient),
              cataleg.py (LOINC, CIAP-2/CIE-10, grupos ATC), formules.py (CKD-EPI 2009 y 2021).
config/       rules.yaml: `rules` (las 8 reglas con "enabled", umbrales, "evidencia" y "pes") y `motor`
              (ecuación FGe, fecha de referencia, FRA, derivación, oportunidades terapéuticas, prioridad).
              Todo pendiente de validar por el médico.
engine/       Motor de reglas determinista (ver "Motor de reglas" más abajo).
scripts/      generate_patients.py: generador sintético (seed 42) -> simulador/datos/demo/; con `--perfil
              realista` llama a cohort_realista.py (cupo calibrado con REGICOR y ENRICA) ->
              simulador/datos/realista/. upload_to_fhir.py: sube (o borra con --esborra) los 100 bundles de
              la cohorte demo al servidor FHIR remoto.
simulador/datos/demo/      DATOS DE LA ESTACIÓN. fhir/ (un bundle FHIR R4 por paciente) y csv/ (patients,
              observations, conditions, medications). Ya no existe la carpeta data/.
simulador/datos/realista/  cohorte realista (1.500 pacientes R0001-R1500, nunca al servidor público): fhir/,
              csv/ y veritat.csv (lo que el generador "sabe" de cada paciente). Parámetros en
              config/cohort_realista.yaml.
tests/        test_fhir_ehr.py (el add-on lee de la estación: conector fhir_ehr, fhirServer, prefetch, iss,
              Bulk Data, memoria por servidor; con una estación simulada y con el servidor Node real del
              simulador; resultados idénticos a los de los ficheros),
              test_cohort_realista.py (prevalencias objetivo y coherencia de la cohorte realista),
              test_connectors.py (FHIR == CSV + 8 casos trampa), test_dades_sintetiques.py (coherencia),
              test_engine.py (fórmulas, casos trampa, selección de escala ESC, CKD Add-on, cortes por edad,
              REGICOR, volante), test_api.py, test_cds_hooks.py, test_export_excel.py, test_fhir_remote.py (servidor simulado).
docs/         dades_sintetiques.md (criterios de generación), decisions.md (decisiones de diseño) y
              cohort_realista.md (fuentes, prevalencias objetivo y obtenidas de la cohorte realista).
api/          ADD-ON. main.py (FastAPI + CORS: /api/cupo, /api/pacientes/{id}, /api/export/excel, /api/rules y el
              servicio CDS Hooks /cds-services; lee de la estación por `iss` / `fhirServer` y guarda el cupo
              en memoria por servidor FHIR), cds_hooks.py (traduce un ResultatPacient a una tarjeta CDS y
              anuncia el prefetch y la interfaz del add-on en el discovery) y rules_store.py (edición validada
              de rules.yaml: lista blanca, rangos, copia en config/backups/).
frontend/     ADD-ON: su interfaz (React + Vite + Tailwind + Lucide, puerto 5173). src/App.jsx (rutas por hash),
              src/launch.js (`iss` y contexto de lanzamiento desde una estación clínica), src/api.js (reenvía
              el `iss` a la API), src/components/: Header ("Datos de: …" y botón "Actualizar"; SIN selectores),
              CupoView (Vista 1, con "Hoy"), PatientView + RenalChart + NoteModal (Vista 2), RulesView
              (Vista 3). Sin lógica clínica: todo viene de la API. Ya NO contiene la estación.
simulador/    SIMULADOR: estación clínica simulada (React + Vite + Tailwind, puerto 5174), aplicación aparte con
              su propio package.json. datos/ (las dos cohortes). servidor-fhir.js (servidor FHIR R4 de solo
              lectura, sin dependencias: plugin de Vite en /fhir y también `node servidor-fhir.js --port N`;
              Patient, $everything, Group del cupo activo, $export Bulk Data y /estacion/cupo),
              src/historia.js (lee ese FHIR y cambia el cupo activo), src/integracion.js (instalación en
              localStorage, discovery, hook patient-view con fhirServer, lanzamiento con iss e intent),
              src/components/: Agenda, Historia, CupoCentro (Configuración → Cupo / centro), Integraciones
              (Configuración → Integraciones), PanelCds, ModalAddon (iframe con el add-on).
start_addon / start_simulador / start_demo (.bat y .sh)   scripts de arranque (ver Comandos).
exports/      cupo_evaluado.xlsx generado con `python -m engine --excel` (no versionado).
```

### Comandos
- Requiere Python >= 3.10. Si el `python` del PATH es más antiguo, crear un venv local
  (`py -3.14 -m venv .venv`) y usar `.venv/Scripts/python`.
- `pip install -r requirements.txt`
- `python scripts/generate_patients.py` regenera los datos (determinista; no editar simulador/datos a mano).
- `python scripts/generate_patients.py --perfil realista --n 1500` regenera la cohorte realista en
  simulador/datos/realista (determinista; opciones `--mrc-sense-dx`, `--prevalenca-ic`, `--llavor`,
  `--sortida`). NO subirla al servidor FHIR público. Tras regenerar, reiniciar la estación (índice en memoria).
- `python -m pytest` ejecuta los tests (182; `test_fhir_ehr.py` arranca el servidor FHIR del simulador con
  Node y se salta esa prueba si no hay Node).
- `python -m engine` resume el cupo priorizado; `python -m engine P003` imprime la nota clínica de un paciente;
  `python -m engine --excel` escribe `exports/cupo_evaluado.xlsx`; `--escala regicor` cambia la calculadora.
  Por defecto lee los ficheros de la cohorte demo; con `--ehr [URL]` lee del servidor FHIR de la estación
  (cupo activo; por defecto http://localhost:5174/fhir, con el simulador arrancado).
- `node simulador/servidor-fhir.js --port 5174` arranca solo el servidor FHIR de la estación (sin interfaz).
- `python -m engine --rules-excel` escribe la hoja de revisión clínica de las reglas (`exports/revision_reglas.xlsx`).
- **Arrancar (scripts en la raíz; `.bat` en Windows, `.sh` en Linux/macOS/Git Bash). Instalan las dependencias
  si faltan; los `.bat` usan `npm.cmd`. Requieren Node.js >= 20 (y Python >= 3.10 el add-on):**
  - `start_addon` arranca SOLO el add-on: API en http://localhost:8000 (`/docs`, `/cds-services`) e interfaz en
    http://localhost:5173. Imprime las URL en la consola. Usa `.venv` si existe. Sin la estación arrancada no
    tiene datos (la interfaz lo dice y ofrece reintentar).
  - `start_simulador` arranca SOLO la estación clínica simulada: http://localhost:5174 (no necesita Python),
    con su servidor FHIR en http://localhost:5174/fhir.
  - `start_demo` arranca los dos (en Windows, cada uno en su ventana, y abre la estación en el navegador;
    `DEMO_SIN_NAVEGADOR=1` para no abrirlo).
  - **Guion de la demo:** estación con el cupo demo y sin add-on -> Configuración → Integraciones -> URL
    `http://localhost:8000` -> Instalar (se ven los servicios del discovery) -> abrir P003 (tarjeta + informe
    de DIRAYA; "Abrir la ficha en CardioAlert AP" abre su ficha) -> botón "CardioAlert AP" de la barra (página
    principal: alertas, "Hoy" y prioridades) -> Configuración → Cupo / centro -> Cupo realista -> botón
    "CardioAlert AP" (el add-on muestra el cupo de 1.500, ~2 s) -> Desinstalar.
- A mano: `python -m uvicorn api.main:app --port 8000`; `cd frontend && npm install && npm run dev`;
  `cd simulador && npm install && npm run dev`. Puertos fijos (`strictPort`): 8000, 5173 y 5174.
  La interfaz del add-on llama a `/api/...` y Vite lo reenvía al puerto 8000 (`VITE_API_PROXY` para cambiarlo).
  `CARDIOALERT_UI_URL` (por defecto http://localhost:5173) es la URL de la interfaz que la API anuncia a la
  estación; `CARDIOALERT_FHIR_URL` (por defecto http://localhost:5174/fhir), la estación de la que lee la API
  si la petición no trae `iss` / `fhirServer`; `CARDIOALERT_FHIR_PERMITIDOS`, expresión regular de los
  servidores FHIR aceptados. `SIMULADOR_DATOS` cambia la carpeta de datos del simulador (con `demo/fhir` y
  `realista/fhir`) y `SIMULADOR_CUPO` (demo | realista), el cupo activo al arrancar.
  En Windows, "localhost" es primero ::1: Vite y el servidor FHIR escuchan ahí; un servidor que solo escuche
  en 127.0.0.1 añade ~2 s a la primera conexión desde Python.
- Servidor FHIR remoto (https://hapi.fhir.org/baseR4, público): `python scripts/upload_to_fhir.py` sube los
  100 pacientes sintéticos con `meta.tag` "the-goats-hackathon" (ya subidos el 14/11/2026; es un
  servidor de pruebas compartido y los datos pueden desaparecer: repetir si la web avisa de que no los encuentra).
  `--esborra` los elimina. SOLO DATOS SINTÉTICOS.

### Motor de reglas (`engine/`)
- `risk_engine.py`: `RiskEngine(connector, config=rules.yaml, data_referencia=None, escala=None)` con
  `avalua(id)`, `avalua_cupo()` (ordenado por prioridad), `avalua_dades(DadesPacient)` y `series_renals(d)`.
  Devuelve `ResultatPacient`: `grup_ordre` / `grup_ordre_text` (orden de la lista de trabajo, 1-4; NO es una
  clasificación), `puntuacio_prioritat` (0-100, ordena dentro del grupo), `text_risc_cv` (categoría de la tabla 5
  ESC 2021 o el motivo por el que no la hay), `estat_risc_cv`, `regicor_referencia`, `nota_calibracio`, `categoria_kdigo`,
  `risc_kdigo`, `estat_renal`, `fge_actual`, `uacr_actual`, `pendent_fge`, `kfre_5a`, `risc_cv`, `escala_usada`,
  `risc_cv_percentatge`, `categoria_risc_cv`, `rang_referencia_cv`, `alertes_actives` (`Alerta`: regla, motiu,
  evidencia "Clase X - ESC/ERA 2026", pes, fonts), `accions_recomanades` (`Accio` con `nota` anti-inercia),
  `avisos`, `ben_tractat`, `objectius_pendents`, `resum` (1 línea), `fonts_dades`, `dades_creuades`,
  `nota_clinica_auto` y `volant_auto` (volante; vacío si no hay nada que pedir).
- `export_excel.py`: libro con hojas Cupo (todas las columnas, textos enteros), Alertas y Resumen.
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
- `puntuacio_prioritat` = suma de `pes` de las alertas + peso KDIGO (máx. 100); solo ordena dentro de cada grupo.
- Textos de salida (alertas, acciones, nota) en castellano; cero umbrales en el código.
- Coeficientes de SCORE2/SCORE2-OP/SCORE2-Diabetes/CKD Add-on contrastados con el paquete R RiskScorescvd;
  los de REGICOR y KFRE y las clases de evidencia de `rules.yaml` están pendientes de verificar con el médico.

### Decisiones tomadas (detalle en docs/decisions.md)
- **Dataset:** 100 pacientes sintéticos (no ~30 ni `pacientes_cupo.csv`), histórico nov 2022 - nov 2026,
  fecha de referencia fija 13/11/2026. Los 8 casos trampa son P001-P008 (ver docs/dades_sintetiques.md).
- **Cohorte realista (docs/cohort_realista.md, decisions.md §12):** 1.500 adultos (>= 18 años) generados
  paciente a paciente con cuotas exactas por edad y sexo. Objetivos: REGICOR (35-54 años: DM 7,4%, HTA 21,2%,
  hipercolesterolemia 32%, fumadores 32,3%; global 14 / 40 / 43 / 24%, IMC 27,2) y ENRICA (ERC 4,8% / 17,4% /
  37,3% por edad; hombres 23,1%, mujeres 7,3%); 2/3 de las ERC sin diagnóstico. La ERC global sale 17,5% (no
  15,1%) porque se priorizan las tasas por edad con una pirámide actual. Resultado del motor: 406
  Bajo-moderado / 340 Alto / 246 Muy alto / 456 menores de 40 / 52 "Faltan datos"; grupos 28 / 224 / 331 / 917;
  detecta 129 de 175 ERC sin diagnosticar. Es un cupo de la estación: se activa en "Configuración → Cupo /
  centro" y el add-on lo lee por Bulk Data (la web del add-on ya NO elige cohorte). `cohort=demo|realista` y
  `GET /api/cohorts` quedan solo para `source=local` (tests). Nunca se sube al servidor FHIR público.
- **Guía ESC 2021 (tabla 5, figuras 3 y 6; detalle en docs/decisions.md §11):** el único nivel de riesgo que
  se muestra es "Bajo-moderado" / "Alto" / "Muy alto" (`categoria_risc_cv`); NO existen ALT/MITJA/BAIX.
  Orden de la lista: 1) alertas urgentes (`possible_ic`, `possible_fra`, `derivacio_nefrologia`), 2) "Muy alto"
  sin tratamiento adecuado, 3) "Alto" sin tratamiento adecuado, 4) resto; dentro, por puntuación. Bloque
  "Hoy: N pacientes prioritarios" (`motor.prioritat.pacients_avui`). Alerta de RCV: 35 puntos "Muy alto", 20
  "Alto" (`risc_cardiovascular.alertes`, editables en la Vista 3), texto propio para >= 70 años aparentemente
  sanos (clase IIb). < 40 años: "Escala SCORE2 no aplicable (<40 años)" y solo reglas renales y pruebas
  pendientes. Sin PAS, colesterol total o HDL: "Faltan datos para calcular el riesgo" + acción. Objetivos de
  tratamiento escalonados: paso 1 (criterio de `ben_tractat`) PAS < 140 y LDL < 100; paso 2 (acción, no
  alerta) PAS < 130 si se tolera y LDL < 70 / < 55 (por eso P007, LDL 68, sigue sin alertas).
  Cohorte demo: 35 Bajo-moderado / 31 Alto / 34 Muy alto; grupos 8 / 26 / 25 / 41.
- **Escala de riesgo CV:** `risc_cardiovascular.escala_per_defecte: totes_dues | score2 | regicor` (por defecto
  `totes_dues`: escala ESC + REGICOR solo como referencia, sin reclasificar; calibración de país de riesgo bajo).
  `score2` es el modo ESC automático: DM2 de 40-69 años -> SCORE2-Diabetes; >= 70 años -> SCORE2-OP;
  < 70 sin diabetes -> SCORE2; + CKD Add-on si hay afectación renal (último FGe < 60 o UACR >= 30) y no es
  una caída aguda. SCORE2-Diabetes NO lleva Add-on por defecto (ya incluye el FGe; `ckd_addon.models`),
  pendiente de validar por el médico. `escala="regicor"` (motor, CLI y API) queda solo para comparaciones
  manuales; la web ya no tiene selector de calculadora.
- **Cortes por edad (ESC), en `talls_per_edat`:** < 50 años 2,5% / 7,5%; 50-69 años 5% / 10%; >= 70 años
  7,5% / 15% (alto / muy alto). REGICOR: `talls_regicor` 10% / 15% (pendiente de validar).
  NO cambiar estos cortes (tabla 5), las fórmulas ni los 100 pacientes de la cohorte demo.
- **Clases de evidencia:** el código no tiene ninguna etiqueta "Clase / Nivel" propia; solo cita el campo
  `evidencia` de `rules.yaml` (si falta, cita únicamente la guía).
- **Datos cruzados entre comunidades:** `dades_creuades` es verdadero si el paciente tiene analíticas de más
  de un origen con formato "Sistema - Comunidad" (p. ej. "eCAP - Catalunya" + "DIRAYA - Andalucía").
- **API y rules.yaml:** `POST /api/rules` solo acepta los parámetros de `api/rules_store.py::EDITABLES`,
  valida rangos y coherencia, prueba el motor con la config nueva y guarda copia en `config/backups/`
  (no versionada) antes de escribir. La API compara `rules.yaml` en cada petición y solo recalcula si cambia.
- **CDS Hooks:** `GET /cds-services` (discovery, con `prefetch`) y `POST /cds-services/cardioalert-patient-view`
  (hook `patient-view`, cuerpo con `context.patientId` y `fhirServer`; los datos se leen de la estación, ver
  "Flujo de datos"). Devuelve una tarjeta por paciente: `summary` (< 140
  caracteres), `indicator` (según `grup_ordre`: 1 = critical, 2 y 3 = warning, 4 = info), `detail` (Markdown: motivo y
  origen del dato) y `suggestions` (acciones del motor, sin `actions`: no escribe en la historia). Siempre
  hay tarjeta, también sin alertas (info). `source` y `scale` en la URL son una extensión propia. El motor
  no se toca: `api/cds_hooks.py` solo traduce. El discovery anuncia la interfaz del add-on en
  `extension["cardioalert-app"].launchUrl` y la tarjeta lleva un enlace `links[type=smart]` a esa URL.
- **Add-on instalable (docs/decisions.md §13):** la estación solo conoce la URL del add-on
  (`http://localhost:8000`). Al instalar llama a `GET {url}/cds-services`, muestra los servicios y guarda la
  instalación en `localStorage` (`estacion-simulada.integracion.v1`). Sin add-on no hay panel ni botón.
  Con add-on: panel "Apoyo a la decisión" (hook `patient-view` al abrir un paciente) y botón "CardioAlert AP"
  en la barra de herramientas, que abre la interfaz del add-on en una ventana modal (iframe) con
  `?iss=<FHIR de la estación>&launch=<contexto>`. **Lanzamiento SMART on FHIR SIMULADO, sin OAuth:** `launch`
  es un JSON en base64url con `patient`, `intent`, `fhirUser`, `practitioner` y `ehr`; `frontend/src/launch.js`
  lo lee: con `intent: "ficha-paciente"` (enlace de la tarjeta) abre la ficha de ese paciente y, si no (botón
  de la barra), la página principal; siempre con una franja de contexto y acceso a la ficha, a "Hoy" y al
  cupo. Si el add-on o su interfaz no responden: aviso en la estación, en el panel y en la ventana; la
  historia sigue funcionando.
- **Estación clínica simulada** (`simulador/`, rutas `#/`, `#/paciente/P003` y `#/configuracion`): historia
  clínica GENÉRICA de atención primaria (sin nombre, logos ni diseño de ningún producto real), con la
  etiqueta visible "Simulación – datos sintéticos" y un profesional simulado (Dra. Carmen Soler). Lee su
  propio servidor FHIR (`/fhir/Patient`, `/fhir/Patient/{id}/$everything`) y muestra los pacientes del cupo
  activo. Los informes de una comunidad distinta de la habitual del paciente (la de la mayoría de sus
  analíticas) llevan "Informe recuperado de otra comunidad" (p. ej. el de DIRAYA de P003), con o sin add-on.
- **Límites actuales:** sin OAuth ni `fhirAuthorization` (simulación); la estación no resuelve el prefetch
  (envía `fhirServer`); el cupo se exporta entero (sin `_since`); el generador sigue en `scripts/` (escribe
  en `simulador/datos`); el servidor FHIR del simulador guarda el índice en memoria.
- **Fuente remota (`source=remote`, HAPI; ya no está en la web):** la API descarga el servidor FHIR una sola
  vez y lo guarda en memoria; si falla, tarda más de 60 s o no tiene nuestros pacientes, vuelve a los
  ficheros locales con un aviso y no reintenta hasta pasados 60 s.
- **Gráfica de la ficha:** dos paneles con el mismo eje de tiempo (FGe y UACR), nunca dos escalas en un
  mismo panel; el color y la forma de cada punto indican el sistema de origen.
- **FGe:** el motor usa **CKD-EPI 2009 sin factor racial** (configurable en `motor.equacio_fge`). El FGe
  guardado en los datos sintéticos sigue siendo el "informado por el laboratorio" con CKD-EPI 2021; el motor
  lo ignora y recalcula (p. ej. Pilar López: 52 informado -> 49 con la 2009).
- **Origen de los datos:** cada `Analitica` lleva `origen` (columna `origen` en CSV, `Observation.performer`
  en FHIR). Por defecto "eCAP - Catalunya"; NT-proBNP "Lab. Hospital"; la analítica de 2025 de José
  Fernández (P003) viene de "DIRAYA - Andalucía" y es la que permite confirmar su albuminuria.
- **Reglas en YAML:** umbrales en config/rules.yaml, nunca hardcodeados en el motor.
- **Conectores:** el motor solo conoce la interfaz `Connector`; añadir una fuente = añadir un conector.
  NO cambiar fórmulas, umbrales, reglas ni resultados del motor: leyendo de la estación, los resultados de las
  dos cohortes y las tres escalas son idénticos byte a byte a los de los ficheros (lo comprueban los tests).
- **Convenciones:** identificadores y docs en catalán; textos clínicos de los datos en castellano.
  Códigos: LOINC (pruebas), CIAP-2 + CIE-10 (diagnósticos), ATC (fármacos, agrupados por prefijo).
- **Git:** commit y push a main tras cada paso que funcione.
