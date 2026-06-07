import PyPDF2
import re
from dotenv import load_dotenv
import os
from openai import OpenAI
import chromadb
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import JSONResponse
import google.generativeai as genai

load_dotenv()

# ==============================================================================
# 1. CONFIGURACIÓN OPENAI (El Bibliotecario Vectorial)
# ==============================================================================
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# ==============================================================================
# 2. CONFIGURACIÓN GOOGLE GEMINI (Motor de Redacción)
# ==============================================================================
google_api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=google_api_key)

# Corrección de Nomenclatura para evadir el Error 404
# Actualizado a la nueva generación flash para garantizar velocidad y estabilidad
gemini_model_flash = genai.GenerativeModel('models/gemini-3.5-flash')
gemini_model_pro = genai.GenerativeModel('models/gemini-3.5-flash') 

# ==============================================================================
# 3. RUTA DEL DISCO DURO (El Volumen de Railway)
# ==============================================================================
DB_PATH = "/app/chroma_db_juridico"

app = FastAPI(title="Cerebro Jurídico EFFICON - Arquitectura Definitiva")

@app.get("/")
async def root():
    return {"mensaje": "Cerebro Jurídico EFFICON operativo. Motores blindados."}

@app.get("/debug_modelos")
async def debug_modelos():
    # Ruta secreta para auditar qué modelos te permite usar exactamente tu API Key
    try:
        lista = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                lista.append(m.name)
        return {"modelos_disponibles": lista}
    except Exception as e:
        return {"error": str(e)}

def leer_pdf(ruta_archivo):
    with open(ruta_archivo, 'rb') as archivo:
        lector = PyPDF2.PdfReader(archivo)
        texto = ''
        for pagina in lector.pages:
            extraido = pagina.extract_text()
            if extraido:
                texto += extraido + '\n'
        return texto

def limpiar_texto(texto):
    texto = re.sub(r'\n\s*\n', '\n\n', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def trocear_texto(texto, tamano_max=3000):
    # Nivel Dios: Guillotina Recursiva Anti-Colapso OpenAI
    parrafos = re.split(r'\n\n+', texto)
    chunks = []
    chunk_actual = ""
    
    for parrafo in parrafos:
        if len(parrafo) > tamano_max:
            oraciones = re.split(r'(?<=\.)\s+', parrafo)
            for oracion in oraciones:
                if len(oracion) > tamano_max:
                    pedazos = [oracion[i:i+tamano_max] for i in range(0, len(oracion), tamano_max)]
                    for pedazo in pedazos:
                        if len(chunk_actual) + len(pedazo) < tamano_max:
                            chunk_actual += pedazo + " "
                        else:
                            if chunk_actual.strip():
                                chunks.append(chunk_actual.strip())
                            chunk_actual = pedazo + " "
                    continue
                if len(chunk_actual) + len(oracion) < tamano_max:
                    chunk_actual += oracion + " "
                else:
                    if chunk_actual.strip():
                        chunks.append(chunk_actual.strip())
                    chunk_actual = oracion + " "
        else:
            if len(chunk_actual) + len(parrafo) < tamano_max:
                chunk_actual += parrafo + "\n\n"
            else:
                if chunk_actual.strip():
                    chunks.append(chunk_actual.strip())
                chunk_actual = parrafo + "\n\n"
                
    if chunk_actual.strip():
        chunks.append(chunk_actual.strip())
        
    return chunks

def etiquetar_documento_maestro(texto_inicial):
    prompt = f"""
    Analiza las primeras páginas de este documento legal y extrae los metadatos.
    Devuelve SOLO el texto en este formato exacto:
    Documento: [Nombre completo de la ley o reglamento]
    Tipo: [Ley, Reglamento, Resolucion, Ordenanza]
    Area: [Tema principal]
    
    Fragmento: {texto_inicial[:1500]}
    """
    try:
        respuesta = gemini_model_flash.generate_content(prompt)
        return parsear_etiquetas(respuesta.text.strip())
    except Exception:
        return {"Documento": "Desconocido", "Tipo": "Desconocido", "Area": "Desconocida"}

def generar_embedding(chunk):
    respuesta = client.embeddings.create(
        model="text-embedding-3-small",
        input=chunk
    )
    return respuesta.data[0].embedding

def parsear_etiquetas(etiquetas_str):
    metadatos = {}
    for linea in etiquetas_str.split('\n'):
        if ':' in linea:
            clave, valor = linea.split(':', 1)
            metadatos[clave.strip('- ').strip()] = valor.strip()
    return metadatos

@app.post("/procesar_pdf")
async def procesar_pdf(file: UploadFile = File(...), entidad: str = Form("General")):
    try:
        ruta_temp = f"temp_{file.filename}"
        contents = await file.read()
        with open(ruta_temp, "wb") as f:
            f.write(contents)
        
        texto_extraido = leer_pdf(ruta_temp)
        texto_limpiado = limpiar_texto(texto_extraido)
        chunks = trocear_texto(texto_limpiado)
        
        db_client = chromadb.PersistentClient(path=DB_PATH)
        # Usamos _v3 para asegurar una tabla limpia sin conflictos residuales
        coleccion = db_client.get_or_create_collection(name="efficon_juridico_v3")
        
        metadatos_base = etiquetar_documento_maestro(texto_limpiado)
        metadatos_base["entidad"] = entidad.strip().upper()
        metadatos_base["archivo"] = file.filename
        
        ids_lista = []
        embeddings_lista = []
        metadatas_lista = []
        documents_lista = []
        
        for i, chunk in enumerate(chunks):
            meta_chunk = metadatos_base.copy()
            meta_chunk["chunk_id"] = i + 1
            
            embeddings_lista.append(generar_embedding(chunk))
            documents_lista.append(chunk)
            metadatas_lista.append(meta_chunk)
            ids_lista.append(f"{file.filename}_chunk_{i+1}")
            
        coleccion.add(
            documents=documents_lista,
            embeddings=embeddings_lista,
            metadatas=metadatas_lista,
            ids=ids_lista
        )
        
        os.remove(ruta_temp) 
        return JSONResponse(content={"mensaje": f"PDF procesado para la entidad {entidad}", "total_chunks": len(chunks)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/listar_documentos")
async def listar_documentos():
    try:
        db_client = chromadb.PersistentClient(path=DB_PATH)
        coleccion = db_client.get_or_create_collection(name="efficon_juridico_v3")
        resultados = coleccion.get(include=["metadatas"])
        
        lista_unica = set()
        for meta in resultados.get('metadatas', []):
            if 'archivo' in meta and 'entidad' in meta:
                lista_unica.add(f"[{meta['entidad']}] - {meta['archivo']}")
                
        return JSONResponse(content={"documentos_cargados": sorted(list(lista_unica))})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/buscar")
async def buscar(body: dict = Body(...)):
    try:
        prompt_completo = body.get("query", "")
        texto_busqueda = body.get("contexto_busqueda", prompt_completo) 
        
        entidad_especifica = body.get("entidad", "").strip().upper()
        tipo_entidad = body.get("tipo_entidad", "").strip().upper()
        
        embedding_pregunta = generar_embedding(texto_busqueda)
        db_client = chromadb.PersistentClient(path=DB_PATH)
        coleccion = db_client.get_or_create_collection(name="efficon_juridico_v3")
        
        lista_busqueda = ["NACIONAL"]
        if tipo_entidad and tipo_entidad != "TODAS":
            lista_busqueda.append(tipo_entidad)
        if entidad_especifica and entidad_especifica != "TODAS":
            lista_busqueda.append(entidad_especifica)
            
        filtro = {"entidad": {"$in": lista_busqueda}}
            
        resultados = coleccion.query(
            query_embeddings=[embedding_pregunta],
            n_results=15, 
            where=filtro
        )
        
        textos_nacionales = []
        textos_sectoriales = []
        textos_locales = []

        if resultados and resultados['documents'] and resultados['documents'][0]:
            for i in range(len(resultados['documents'][0])):
                archivo = resultados['metadatas'][0][i].get('archivo', 'Normativa')
                capa_origen = resultados['metadatas'][0][i].get('entidad', 'Desconocida')
                texto_chunk = resultados['documents'][0][i]
                
                if capa_origen == "NACIONAL":
                    textos_nacionales.append(f"<documento origen='{archivo}'>\n{texto_chunk}\n</documento>")
                elif capa_origen == tipo_entidad:
                    textos_sectoriales.append(f"<documento origen='{archivo}'>\n{texto_chunk}\n</documento>")
                else:
                    textos_locales.append(f"<documento origen='{archivo}'>\n{texto_chunk}\n</documento>")

        textos_legales_xml = "<marco_legal>\n"
        if textos_locales:
            textos_legales_xml += f"<jerarquia_1_prioridad_local entidad='{entidad_especifica}'>\n" + "\n".join(textos_locales) + "\n</jerarquia_1_prioridad_local>\n"
        if textos_sectoriales:
            textos_legales_xml += f"<jerarquia_2_media_sectorial sector='{tipo_entidad}'>\n" + "\n".join(textos_sectoriales) + "\n</jerarquia_2_media_sectorial>\n"
        if textos_nacionales:
            textos_legales_xml += f"<jerarquia_3_base_nacional>\n" + "\n".join(textos_nacionales) + "\n</jerarquia_3_base_nacional>\n"
        textos_legales_xml += "</marco_legal>"
        
        textos_legales_mostrar = textos_legales_xml

        if "{{Contexto_Legal_ChromaDB}}" in prompt_completo:
            prompt_final = prompt_completo.replace("{{Contexto_Legal_ChromaDB}}", textos_legales_xml)
        else:
            prompt_final = f"{prompt_completo}\n\nCONTEXTO LEGAL:\n{textos_legales_xml}"
            
        instruccion_sistema = f"""
        Eres un abogado consultor en contratación pública de PROESTRATEGIA.
        Analiza el caso basándote EXCLUSIVAMENTE en el <marco_legal> proporcionado en formato XML.
        
        REGLAS DE RESOLUCIÓN DE CONFLICTOS Y SUBSUNCIÓN LEGAL:
        1. JERARQUÍA: Las normas en <jerarquia_1_prioridad_local> prevalecen. Las <jerarquia_2_media_sectorial> complementan. Las <jerarquia_3_base_nacional> son el marco general.
        2. SUBSUNCIÓN OBLIGATORIA: Tu tarea es argumentar y justificar legalmente la contratación. Conecta lógicamente la 'Necesidad' del usuario con las competencias, fines o directrices presentes en los artículos del <marco_legal>.
        3. REDACCIÓN NATURAL: Menciona el nombre de la normativa de forma fluida en el texto (ej. "De acuerdo a la Constitución..."). ESTÁ ESTRICTAMENTE PROHIBIDO incluir referencias técnicas, corchetes o nombres de archivo como "(origen: archivo.pdf)".
        4. PROHIBICIÓN DE ALUCINACIÓN: Prohibido inventar artículos o leyes que no estén en el XML.
        5. Si el XML está completamente vacío, responde: "Normativa insuficiente para emitir criterio".
        """
        
        prompt_gemini = f"INSTRUCCIONES DE SISTEMA:\n{instruccion_sistema}\n\nSOLICITUD DEL USUARIO:\n{prompt_final}"

        respuesta = gemini_model_pro.generate_content(
            prompt_gemini,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                top_p=0.1
            )
        )
        
        return JSONResponse(content={
            "argumentacion": respuesta.text.strip(),
            "archivos_consultados": resultados['metadatas'][0] if resultados.get('metadatas') else [],
            "textos_crudos_chromadb": textos_legales_mostrar
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)