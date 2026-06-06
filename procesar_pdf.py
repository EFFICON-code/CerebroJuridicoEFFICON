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

# 1. CONFIGURACIÓN OPENAI (Para la Búsqueda Matemática Vectorial)
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# 2. CONFIGURACIÓN GOOGLE GEMINI (Doble Motor)
google_api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=google_api_key)

# Motor 1: Ultra rápido y económico para extraer metadatos iniciales
gemini_model_flash = genai.GenerativeModel('gemini-2.5-flash')
# Motor 2: Nivel Dios en razonamiento para el análisis jurídico, acatamiento XML y prevención de alucinaciones
gemini_model_pro = genai.GenerativeModel('gemini-1.5-pro')

# 3. RUTA DEL DISCO DURO (El Volumen de Railway)
DB_PATH = "/app/chroma_db_juridico"

app = FastAPI(title="Cerebro Jurídico EFFICON - Arquitectura XML Estricta")

@app.get("/")
async def root():
    return {"mensaje": "Cerebro Jurídico EFFICON listo y blindado contra alucinaciones"}

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
    # Nivel Dios: Guillotina Recursiva y Segura para OpenAI
    # tamano_max=3000 caracteres equivalen a ~800 tokens (Súper seguro, el límite es 8192)
    
    parrafos = re.split(r'\n\n+', texto)
    chunks = []
    chunk_actual = ""
    
    for parrafo in parrafos:
        # PLAN B: Si un párrafo (o el documento entero por culpa de PyPDF2) es un monstruo gigante
        if len(parrafo) > tamano_max:
            # Lo partimos por puntos (oraciones) para no romper el sentido legal
            oraciones = re.split(r'(?<=\.)\s+', parrafo)
            for oracion in oraciones:
                # PLAN C: Si incluso una "oración" es infinita (ej. una tabla sin puntos), la cortamos bruscamente
                if len(oracion) > tamano_max:
                    # Dividimos la oración gigante en tajos exactos de tamano_max
                    pedazos = [oracion[i:i+tamano_max] for i in range(0, len(oracion), tamano_max)]
                    for pedazo in pedazos:
                        if len(chunk_actual) + len(pedazo) < tamano_max:
                            chunk_actual += pedazo + " "
                        else:
                            if chunk_actual.strip():
                                chunks.append(chunk_actual.strip())
                            chunk_actual = pedazo + " "
                    continue # Saltamos a la siguiente iteración

                # Agrupación normal de oraciones seguras
                if len(chunk_actual) + len(oracion) < tamano_max:
                    chunk_actual += oracion + " "
                else:
                    if chunk_actual.strip():
                        chunks.append(chunk_actual.strip())
                    chunk_actual = oracion + " "
        else:
            # PLAN A: Comportamiento normal para párrafos bien formateados
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
        # Flash es perfecto para esta tarea simple de extracción
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
        
        # Uso del nuevo Chunking Semántico
        chunks = trocear_texto(texto_limpiado)
        
        db_client = chromadb.PersistentClient(path=DB_PATH)
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
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
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
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
        
        # --- CAPTURA DE VARIABLES (LAS 3 CAPAS) ---
        entidad_especifica = body.get("entidad", "").strip().upper()
        tipo_entidad = body.get("tipo_entidad", "").strip().upper()
        
        # 1. BÚSQUEDA VECTORIAL (El Bibliotecario - OpenAI)
        embedding_pregunta = generar_embedding(texto_busqueda)
        db_client = chromadb.PersistentClient(path=DB_PATH)
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        lista_busqueda = ["NACIONAL"]
        
        if tipo_entidad and tipo_entidad != "TODAS":
            lista_busqueda.append(tipo_entidad)
            
        if entidad_especifica and entidad_especifica != "TODAS":
            lista_busqueda.append(entidad_especifica)
            
        filtro = {"entidad": {"$in": lista_busqueda}}
            
        resultados = coleccion.query(
            query_embeddings=[embedding_pregunta],
            n_results=15, # Ampliado para capturar de las 3 gavetas con seguridad
            where=filtro
        )
        
        cantidad = len(resultados['documents'][0]) if resultados and resultados['documents'] and resultados['documents'][0] else 0
        print(f"🕵️ AUDITORÍA DE CHUNKS -> Gavetas abiertas: {lista_busqueda} | Chunks extraídos: {cantidad}")
        
        # --- ORDENAMIENTO JERÁRQUICO Y ESTRUCTURACIÓN XML ---
        textos_nacionales = []
        textos_sectoriales = []
        textos_locales = []

        if resultados and resultados['documents'] and resultados['documents'][0]:
            for i in range(len(resultados['documents'][0])):
                archivo = resultados['metadatas'][0][i].get('archivo', 'Normativa')
                capa_origen = resultados['metadatas'][0][i].get('entidad', 'Desconocida')
                texto_chunk = resultados['documents'][0][i]
                
                # Clasificamos el chunk en su respectiva gaveta virtual
                if capa_origen == "NACIONAL":
                    textos_nacionales.append(f"<documento origen='{archivo}'>\n{texto_chunk}\n</documento>")
                elif capa_origen == tipo_entidad:
                    textos_sectoriales.append(f"<documento origen='{archivo}'>\n{texto_chunk}\n</documento>")
                else:
                    textos_locales.append(f"<documento origen='{archivo}'>\n{texto_chunk}\n</documento>")

        # Ensamblamos el XML dando prioridad a la normativa de la entidad específica
        textos_legales_xml = "<marco_legal>\n"
        if textos_locales:
            textos_legales_xml += f"<jerarquia_1_prioridad_local entidad='{entidad_especifica}'>\n" + "\n".join(textos_locales) + "\n</jerarquia_1_prioridad_local>\n"
        if textos_sectoriales:
            textos_legales_xml += f"<jerarquia_2_media_sectorial sector='{tipo_entidad}'>\n" + "\n".join(textos_sectoriales) + "\n</jerarquia_2_media_sectorial>\n"
        if textos_nacionales:
            textos_legales_xml += f"<jerarquia_3_base_nacional>\n" + "\n".join(textos_nacionales) + "\n</jerarquia_3_base_nacional>\n"
        textos_legales_xml += "</marco_legal>"
        
        # Mantener compatibilidad con el front-end
        textos_legales_mostrar = textos_legales_xml

        if "{{Contexto_Legal_ChromaDB}}" in prompt_completo:
            prompt_final = prompt_completo.replace("{{Contexto_Legal_ChromaDB}}", textos_legales_xml)
        else:
            prompt_final = f"{prompt_completo}\n\nCONTEXTO LEGAL:\n{textos_legales_xml}"
            
        instruccion_sistema = f"""
        Eres un auditor jurídico estricto en contratación pública ecuatoriana.
        Analiza el caso basándote EXCLUSIVAMENTE en el <marco_legal> proporcionado en formato XML.
        
        REGLAS DE RESOLUCIÓN DE CONFLICTOS Y JERARQUÍA:
        1. PRIORIDAD ABSOLUTA: Las normas contenidas en <jerarquia_1_prioridad_local> PREVALECEN sobre todas las demás. Si hay contradicción, manda la regla local.
        2. SUPLETORIEDAD: Las normas en <jerarquia_3_base_nacional> se usan como marco procedimental general. Si la normativa local no especifica algo, usa la nacional.
        3. PROHIBICIÓN DE ALUCINACIÓN: Tienes estrictamente prohibido inventar números de artículos o incisos. Al justificar resoluciones o requerimientos técnicos, utiliza exactamente el contenido literal provisto (por ejemplo, el texto exacto de los artículos de la LOSNCP y su Reglamento General o las Ordenanzas Locales extraídas).
        4. CITA DE ORIGEN: Cada vez que apliques una regla, debes citar explícitamente el atributo 'origen' de la etiqueta <documento>.
        5. Si la base legal para resolver la solicitud del usuario no existe explícitamente en el <marco_legal>, NO asumas ni inventes nada. Debes responder textualmente: "Normativa insuficiente para emitir criterio".
        """
        
        prompt_gemini = f"INSTRUCCIONES DE SISTEMA:\n{instruccion_sistema}\n\nSOLICITUD DEL USUARIO:\n{prompt_final}"

        # 2. REDACCIÓN Y RAZONAMIENTO (El Abogado - Gemini 1.5 Pro)
        respuesta = gemini_model_pro.generate_content(
            prompt_gemini,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0, # Temperatura 0 obligatoria para estricto apego legal
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