import streamlit as st
import requests

API_URL = "https://cerebrojuridicoefficon-production.up.railway.app"  

st.set_page_config(page_title="EFFICON Jurídico", layout="centered")
st.title("⚖️ EFFICON - Cerebro Jurídico Institucional")

st.markdown("### 1. Cargar Normativa")
entidad_input = st.text_input("Nombre de la Entidad (Ej: GAD Loja, SERCOP, Bomberos):", value="GENERAL")
uploaded_file = st.file_uploader("Sube el documento legal (PDF)", type="pdf")

if uploaded_file is not None:
    if st.button("Procesar y Memorizar PDF"):
        with st.spinner("Leyendo, troceando y generando embeddings... esto tomará unos segundos."):
            # Añadimos el dato de la Entidad al envío
            datos = {"entidad": entidad_input}
            archivos = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            
            response = requests.post(f"{API_URL}/procesar_pdf", data=datos, files=archivos, verify=False)
            
            if response.status_code == 200:
                st.success(f"¡Documento memorizado con éxito para la entidad: {entidad_input}!")
            else:
                st.error(f"Error del servidor: {response.text}")

st.divider()

st.markdown("### 2. Biblioteca de EFFICON")
if st.button("Ver Documentos Cargados en el Cerebro"):
    response = requests.get(f"{API_URL}/listar_documentos")
    if response.status_code == 200:
        data = response.json()
        if data.get("documentos_cargados"):
            st.success("Archivos actualmente en memoria:")
            for doc in data["documentos_cargados"]:
                st.markdown(f"- **{doc}**")
        else:
            st.info("La base de datos vectorial está vacía.")
    else:
        st.error(f"Error al conectar con la base de datos: {response.text}")