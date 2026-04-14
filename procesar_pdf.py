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

# 2. CONFIGURACIÓN GOOGLE GEMINI (Para la Redacción Ultra Rápida)
google_api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=google_api_key)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# 3. RUTA DEL DISCO DURO (El Volumen de Railway)
DB_PATH = "/app/chroma_db_juridico"

app = FastAPI(title="Cerebro Jurídico EFFICON - Gemini Flash")

@app.get("/")
async def root():
    return {"mensaje": "Cerebro Jurídico EFFICON listo con Gemini 2.5 Flash"}

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

def trocear_texto(texto, tamano_min=300, tamano_max=800):
    chunks = []
    palabras = texto.split()
    chunk_actual = []
    conteo_actual = 0
    for palabra in palabras:
        chunk_actual.append(palabra)
        conteo_actual += len(palabra) + 1
        if conteo_actual >= tamano_max:
            chunks.append(' '.join(chunk_actual))
            chunk_actual = []
            conteo_actual = 0
    if chunk_actual:
        chunks.append(' '.join(chunk_actual))
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
        respuesta = gemini_model.generate_content(prompt)
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
        entidad_filtro = body.get("entidad", "TODAS")
        
        # 1. BÚSQUEDA VECTORIAL (El Bibliotecario - OpenAI)
        embedding_pregunta = generar_embedding(texto_busqueda)
        db_client = chromadb.PersistentClient(path=DB_PATH)
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        filtro = {}
        if entidad_filtro != "TODAS":
            filtro = {"entidad": entidad_filtro.strip().upper()}
            
        resultados = coleccion.query(
            query_embeddings=[embedding_pregunta],
            n_results=7,
            where=filtro if filtro else None
        )
        
        # --- EL CHIVATO DE LOGS ---
        cantidad = len(resultados['documents'][0]) if resultados and resultados['documents'] and resultados['documents'][0] else 0
        print(f"🕵️ AUDITORÍA DE CHUNKS -> Entidad buscada: '{entidad_filtro}' | Chunks extraídos de la BD: {cantidad}")
        # --------------------------
        
        textos_legales = ""
        if resultados and resultados['documents'] and resultados['documents'][0]:
            for i in range(len(resultados['documents'][0])):
                archivo = resultados['metadatas'][0][i].get('archivo', 'Normativa')
                textos_legales += f"\n--- EXTRAÍDO DE: {archivo} ---\n{resultados['documents'][0][i]}\n"
        
        if "{{Contexto_Legal_ChromaDB}}" in prompt_completo:
            prompt_final = prompt_completo.replace("{{Contexto_Legal_ChromaDB}}", textos_legales)
        else:
            prompt_final = f"{prompt_completo}\n\nCONTEXTO LEGAL ESTRICTO:\n{textos_legales}"
            
        instruccion_sistema = """
        Eres un abogado experto en contratación pública en Ecuador. Redactas informes de necesidad.
        Regla 1: Basa tu argumentación en el CONTEXTO LEGAL ESTRICTO provisto.
        Regla 2: Si el contexto legal está vacío, redacta usando principios generales, sin inventar artículos.
        Regla 3: NUNCA insertes advertencias de error en la redacción final.
        """
        
        prompt_gemini = f"INSTRUCCIONES DE SISTEMA:\n{instruccion_sistema}\n\nSOLICITUD DEL USUARIO:\n{prompt_final}"

        # 2. REDACCIÓN Y RAZONAMIENTO (El Abogado - Gemini 2.5 Flash)
        respuesta = gemini_model.generate_content(
            prompt_gemini,
            generation_config=genai.types.GenerationConfig(temperature=0.1)
        )
        
        return JSONResponse(content={
            "argumentacion": respuesta.text.strip(),
            "archivos_consultados": resultados['metadatas'][0] if resultados.get('metadatas') else [],
            "textos_crudos_chromadb": textos_legales
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)