import streamlit as st
import requests
import urllib3

# Silenciar las advertencias de conexión SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# LA URL DE SU CEREBRO EN RAILWAY
API_URL = "https://cerebrojuridicoefficon-production.up.railway.app"  

st.set_page_config(page_title="EFFICON Jurídico", layout="wide", page_icon="⚖️")
st.title("⚖️ EFFICON - GESTOR DE NORMATIVA MULTIENTIDAD")

tab1, tab2, tab3 = st.tabs(["📥 1. Inyectar Normativa (Clasificada)", "💬 2. Chat de Prueba", "🔍 3. MODO AUDITOR (Rayos X)"])

# ==========================================
# PESTAÑA 1: GESTIÓN DE NORMATIVAS (NUEVO DISEÑO 3 CAPAS)
# ==========================================
with tab1:
    col1, col2 = st.columns([1.2, 1])
    
    with col1:
        st.markdown("### 📥 Clasificación de Nuevo Documento")
        st.markdown("Seleccione el alcance de la ley para guardarla en la gaveta correcta:")
        
        # 1. El Selector Guiado
        tipo_alcance = st.radio(
            "Nivel Jerárquico:",
            [
                "🌍 GENERAL / NACIONAL (Aplica a todo el Estado. Ej: LOSNCP, Constitución)",
                "🏢 SECTORIAL (Aplica a un tipo de entidad. Ej: COOTAD, Ley de Bomberos)",
                "📍 INTERNA / ESPECÍFICA (Aplica solo a una institución. Ej: Ordenanza Municipio Loja)"
            ]
        )
        
        st.markdown("---")
        
        # 2. Lógica dinámica de etiquetas (CORREGIDA CON KEYS ÚNICOS)
        etiqueta_final = ""
        
        if "GENERAL" in tipo_alcance:
            st.info("📌 Esta normativa se guardará en la gaveta NACIONAL. Se usará como base para todos los informes.")
            etiqueta_final = "NACIONAL"
            
        elif "SECTORIAL" in tipo_alcance:
            st.info("📌 Guardaremos esto para un grupo. Ejemplos válidos: GAD, BOMBEROS, HOSPITALES, MINISTERIOS.")
            # AÑADIMOS key="input_sector" PARA EVITAR EL ERROR ROJO
            sector_input = st.text_input("Escriba el Tipo de Entidad (Sector):", placeholder="Ej: BOMBEROS", key="input_sector")
            etiqueta_final = sector_input.strip().upper()
            
        elif "INTERNA" in tipo_alcance:
            st.info("📌 Guardaremos esto como regla local. Debe coincidir exactamente con el nombre de su cliente en Excel.")
            # AÑADIMOS key="input_interna" PARA EVITAR EL ERROR ROJO
            institucion_input = st.text_input("Escriba el Nombre Exacto de la Institución:", placeholder="Ej: MUNICIPIO LOJA", key="input_interna")
            etiqueta_final = institucion_input.strip().upper()

        uploaded_file = st.file_uploader("Sube el documento legal (PDF)", type="pdf")

        # 3. Botón de Procesamiento
        if uploaded_file is not None:
            # Validación de seguridad
            if not etiqueta_final:
                st.warning("⚠️ Por favor, complete el nombre o tipo de entidad antes de subir el documento.")
            else:
                if st.button(f"Memorizar en gaveta: [{etiqueta_final}]", use_container_width=True):
                    with st.spinner(f"🧠 Guardando {uploaded_file.name} como normativa {etiqueta_final}..."):
                        datos = {"entidad": etiqueta_final}
                        archivos = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                        try:
                            response = requests.post(f"{API_URL}/procesar_pdf", data=datos, files=archivos, verify=False)
                            if response.status_code == 200:
                                st.success(f"¡Éxito! Documento blindado y guardado bajo la etiqueta: **{etiqueta_final}**")
                            else:
                                st.error(f"Error del servidor: {response.text}")
                        except Exception as e:
                            st.error(f"Error de conexión: {e}")

    with col2:
        st.markdown("### 📚 Índice de Gavetas")
        st.info("Revise cómo está organizada su base de datos actual.")
        if st.button("Actualizar Índice de Archivos", use_container_width=True):
            try:
                response = requests.get(f"{API_URL}/listar_documentos", verify=False)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("documentos_cargados"):
                        st.success("Archivos detectados en el Disco Duro:")
                        for doc in data["documentos_cargados"]:
                            st.markdown(f"- `{doc}`")
                    else:
                        st.warning("El Disco Duro está vacío. Suba un PDF.")
                else:
                    st.error("Error al leer la base de datos.")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

# ==========================================
# PESTAÑA 2: EL CHAT JURÍDICO (ACTUALIZADO A 3 CAPAS)
# ==========================================
with tab2:
    st.markdown("### 💬 Simulador de Consulta")
    st.markdown("Pruebe cómo responde la IA cruzando las leyes generales con las de su entidad específica.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        simulador_tipo = st.text_input("1. Filtrar Tipo (Ej: BOMBEROS):", value="")
    with col_b:
        simulador_entidad = st.text_input("2. Filtrar Entidad (Ej: BOMBEROS PANGUI):", value="")
    
    if prompt := st.chat_input("Escribe tu consulta legal (Ej: ¿Cuál es el proceso para comprar repuestos?)..."):
        st.info(f"Analizando cruce legal para: Tipo [{simulador_tipo}] + Entidad [{simulador_entidad}]")
        with st.spinner("Leyendo las 3 gavetas vectoriales..."):
            try:
                payload = {
                    "query": prompt, 
                    "contexto_busqueda": prompt, 
                    "tipo_entidad": simulador_tipo.upper(),
                    "entidad": simulador_entidad.upper()
                }
                res = requests.post(f"{API_URL}/buscar", json=payload, verify=False)
                if res.status_code == 200:
                    st.markdown("### Respuesta de EFFICON:")
                    st.write(res.json().get("argumentacion", "Sin respuesta."))
                else:
                    st.error("Error en el servidor.")
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# PESTAÑA 3: EL MODO AUDITOR (LA PRUEBA)
# ==========================================
with tab3:
    st.markdown("### 🔍 Radiografía de Extracción (Chunks)")
    
    busqueda_cruda = st.text_input("Escriba concepto a buscar (Ej: 'garantía', 'viáticos'):")
    col_x, col_y = st.columns(2)
    with col_x:
        auditor_tipo = st.text_input("Tipo de Entidad (Sector):", value="", key="aud_tipo")
    with col_y:
        auditor_entidad = st.text_input("Entidad Específica:", value="", key="aud_ent")
    
    if st.button("Buscar Chunks en la Base de Datos", use_container_width=True):
        if busqueda_cruda:
            with st.spinner("Abriendo gavetas solicitadas..."):
                try:
                    payload = {
                        "query": "Ignorar", 
                        "contexto_busqueda": busqueda_cruda, 
                        "tipo_entidad": auditor_tipo.upper(),
                        "entidad": auditor_entidad.upper()
                    }
                    res = requests.post(f"{API_URL}/buscar", json=payload, verify=False)
                    if res.status_code == 200:
                        datos = res.json()
                        chunks = datos.get("textos_crudos_chromadb", "")
                        if chunks.strip():
                            st.success("¡Leyes encontradas! Estos párrafos se envían a la IA:")
                            st.text_area("Evidencia de Chunks (Solo Lectura):", value=chunks, height=400)
                        else:
                            st.error("❌ Las gavetas seleccionadas no tienen leyes sobre este tema.")
                except Exception as e:
                    st.error(f"Error de conexión con Railway: {e}")