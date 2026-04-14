import streamlit as st
import requests

API_URL = "https://cerebrojuridicoefficon-production.up.railway.app"  

st.set_page_config(page_title="EFFICON Jurídico", layout="wide")
st.title("⚖️ EFFICON - Cerebro Jurídico Institucional")

# Dividimos la interfaz en 3 pestañas profesionales
tab1, tab2, tab3 = st.tabs(["📥 1. Inyectar Normativa", "💬 2. Consultar a EFFICON", "🔍 3. MODO AUDITOR (Rayos X)"])

# ==========================================
# PESTAÑA 1: GESTIÓN DE NORMATIVAS
# ==========================================
with tab1:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 📥 Subir Nuevo Documento")
        entidad_input = st.text_input("Nombre de la Entidad (Ej: SERCOP, BOMBEROS):", value="GENERAL")
        uploaded_file = st.file_uploader("Sube el documento legal (PDF)", type="pdf")

        if uploaded_file is not None:
            if st.button("Procesar y Memorizar PDF", use_container_width=True):
                with st.spinner("🧠 Leyendo, troceando y guardando en Volumen..."):
                    datos = {"entidad": entidad_input.upper()}
                    archivos = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                    try:
                        response = requests.post(f"{API_URL}/procesar_pdf", data=datos, files=archivos, verify=False)
                        if response.status_code == 200:
                            st.success(f"¡Documento guardado en ChromaDB para: {entidad_input}!")
                        else:
                            st.error(f"Error del servidor: {response.text}")
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")

    with col2:
        st.markdown("### 📚 Índice de la Base de Datos")
        if st.button("Ver Índice de Archivos Guardados", use_container_width=True):
            try:
                response = requests.get(f"{API_URL}/listar_documentos")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("documentos_cargados"):
                        st.success("Archivos detectados en el Disco Duro (Volume):")
                        for doc in data["documentos_cargados"]:
                            st.markdown(f"- `{doc}`")
                    else:
                        st.warning("El Disco Duro está vacío. Suba un PDF.")
                else:
                    st.error("Error al leer la base de datos.")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

# ==========================================
# PESTAÑA 2: EL CHAT JURÍDICO
# ==========================================
with tab2:
    st.markdown("### 💬 Chat con el Cerebro")
    filtro_entidad = st.text_input("Filtrar búsqueda por Entidad:", value="TODAS", key="filtro_chat")
    
    if prompt := st.chat_input("Escribe tu consulta legal..."):
        st.info(f"Buscando respuesta para: {prompt}")
        with st.spinner("Analizando base de datos vectorial..."):
            try:
                payload = {"query": prompt, "contexto_busqueda": prompt, "entidad": filtro_entidad.upper()}
                res = requests.post(f"{API_URL}/buscar", json=payload)
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
    st.markdown("### 🔍 Radiografía de ChromaDB")
    st.info("Esta herramienta puentea a la IA. Le muestra exactamente los trozos de texto (chunks) crudos que el motor de búsqueda matemática encuentra en su disco duro.")
    
    busqueda_cruda = st.text_input("Escriba una palabra clave o artículo para buscar en los chunks (Ej: 'garantía', 'incendios', 'Art. 45'):")
    entidad_auditor = st.text_input("Filtrar por Entidad (Dejar en 'TODAS' para buscar globalmente):", value="TODAS", key="entidad_auditor")
    
    if st.button("Buscar Chunks Crudos", use_container_width=True):
        if busqueda_cruda:
            with st.spinner("Extrayendo texto directo del disco duro..."):
                try:
                    payload = {"query": "Ignorar", "contexto_busqueda": busqueda_cruda, "entidad": entidad_auditor.upper()}
                    res = requests.post(f"{API_URL}/buscar", json=payload)
                    
                    if res.status_code == 200:
                        datos_respuesta = res.json()
                        chunks = datos_respuesta.get("textos_crudos_chromadb", "")
                        
                        if chunks.strip():
                            st.success("¡Base de datos respondiendo! Estos son los párrafos exactos que se le envían a la IA:")
                            st.text_area("Evidencia de Chunks (Solo Lectura):", value=chunks, height=400)
                        else:
                            st.error("❌ La base de datos no encontró ningún párrafo que contenga esa información. Verifique que la Entidad esté bien escrita o que el PDF se haya subido correctamente.")
                    else:
                        st.error(f"Error del servidor: {res.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("Escriba algo para buscar.")