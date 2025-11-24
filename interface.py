import streamlit as st
import requests

API_URL = "https://cerebrojuridicoefficon-production.up.railway.app"  # Tu enlace

st.title("EFFICON - Subir y Ver Normativas")

# Subir PDF
uploaded_file = st.file_uploader("Sube un PDF", type="pdf")
if uploaded_file is not None:
    if st.button("Procesar PDF"):
        st.info("Subiendo y procesando...")
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
        response = requests.post(f"{API_URL}/procesar_pdf", files=files)
        if response.status_code == 200:
            st.success("PDF procesado exitosamente!")
            st.json(response.json())
        else:
            st.error(f"Error: {response.text}")

# Ver documentos procesados
if st.button("Ver Documentos Cargados"):
    response = requests.get(f"{API_URL}/listar_documentos")
    if response.status_code == 200:
        data = response.json()
        if data["documentos_cargados"]:
            st.success("Documentos procesados:")
            for doc in data["documentos_cargados"]:
                st.write(f"- {doc}")
        else:
            st.info("No hay documentos cargados aún.")
    else:
        st.error(f"Error al listar: {response.text}")