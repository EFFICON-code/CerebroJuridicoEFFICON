import PyPDF2
import re
from dotenv import load_dotenv
import os
from openai import OpenAI
import chromadb
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import JSONResponse

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

app = FastAPI(title="Cerebro Jurídico EFFICON")

@app.get("/")
async def root():
    return {"mensaje": "Cerebro Jurídico EFFICON listo y operando"}

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

# CORRECCIÓN 3: Leemos con la IA una SOLA VEZ por documento para ahorrar dinero y tiempo
def etiquetar_documento_maestro(texto_inicial):
    prompt = f"""
    Analiza las primeras páginas de este documento legal y extrae los metadatos.
    Devuelve SOLO el texto en este formato exacto (sin asteriscos ni comillas):
    Documento: [Nombre completo de la ley o reglamento]
    Tipo: [Ley, Reglamento, Resolucion, Ordenanza]
    Area: [Tema principal]
    
    Fragmento: {texto_inicial[:1500]}
    """
    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini", # Usamos la versión mini para metadatos (más rápida y barata)
            messages=[{"role": "user", "content": prompt}]
        )
        return parsear_etiquetas(respuesta.choices[0].message.content.strip())
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
# NUEVO: Recibimos el parámetro 'entidad' desde el formulario
async def procesar_pdf(file: UploadFile = File(...), entidad: str = Form("General")):
    try:
        ruta_temp = f"temp_{file.filename}"
        contents = await file.read()
        with open(ruta_temp, "wb") as f:
            f.write(contents)
        
        texto_extraido = leer_pdf(ruta_temp)
        texto_limpiado = limpiar_texto(texto_extraido)
        chunks = trocear_texto(texto_limpiado)
        
        # CORRECCIÓN 4: Ruta local persistente y segura
        db_client = chromadb.PersistentClient(path="./chroma_db_juridico")
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        # Sacamos los metadatos generales 1 sola vez
        metadatos_base = etiquetar_documento_maestro(texto_limpiado)
        metadatos_base["entidad"] = entidad.strip().upper() # Etiqueta de la Institución
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
            
            # CORRECCIÓN 1: ID Único a prueba de sobreescrituras
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

# CORRECCIÓN 2: El endpoint fantasma ya existe y devuelve los archivos
@app.get("/listar_documentos")
async def listar_documentos():
    try:
        db_client = chromadb.PersistentClient(path="./chroma_db_juridico")
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        # Obtenemos los metadatos de todo lo guardado
        resultados = coleccion.get(include=["metadatas"])
        
        lista_unica = set()
        for meta in resultados.get('metadatas', []):
            if 'archivo' in meta and 'entidad' in meta:
                # Agrupamos por Archivo y Entidad
                lista_unica.add(f"[{meta['entidad']}] - {meta['archivo']}")
                
        return JSONResponse(content={"documentos_cargados": sorted(list(lista_unica))})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/buscar")
async def buscar(body: dict = Body(...)):
    try:
        # Recibimos el prompt gigante de Excel y el texto específico para buscar
        prompt_completo = body.get("query", "")
        texto_busqueda = body.get("contexto_busqueda", prompt_completo) 
        entidad_filtro = body.get("entidad", "TODAS")
        
        # 1. BÚSQUEDA VECTORIAL LIMPIA (Solo busca el Objeto y la Necesidad)
        embedding_pregunta = generar_embedding(texto_busqueda)
        db_client = chromadb.PersistentClient(path="./chroma_db_juridico")
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        filtro = {}
        if entidad_filtro != "TODAS":
            filtro = {"entidad": entidad_filtro.strip().upper()}
            
        resultados = coleccion.query(
            query_embeddings=[embedding_pregunta],
            n_results=7, # Aumentamos a 7 párrafos legales para mayor riqueza
            where=filtro if filtro else None
        )
        
        # 2. CONSTRUIR EL EXPEDIENTE LEGAL
        textos_legales = ""
        if resultados and resultados['documents'] and resultados['documents'][0]:
            for i in range(len(resultados['documents'][0])):
                archivo = resultados['metadatas'][0][i].get('archivo', 'Ley Desconocida')
                textos_legales += f"\n--- EXTRAÍDO DE: {archivo} ---\n{resultados['documents'][0][i]}\n"
        
        # 3. INYECCIÓN EXACTA EN SU EXCEL
        # Aquí reemplazamos la llave {{Contexto_Legal_ChromaDB}} que usted puso en la celda B188
        if "{{Contexto_Legal_ChromaDB}}" in prompt_completo:
            prompt_final = prompt_completo.replace("{{Contexto_Legal_ChromaDB}}", textos_legales)
        else:
            prompt_final = f"{prompt_completo}\n\nCONTEXTO LEGAL ESTRICTO:\n{textos_legales}"
            
        # 4. LLAMADA A LA IA CON MODO "JUEZ ESTRICTO" (Cero Alucinaciones)
        respuesta = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.0, # 0.0 SIGNIFICA: NO INVENTES NADA, SOLO USA LOS HECHOS
            messages=[
                {"role": "system", "content": "Eres un asistente jurídico implacable. Tu regla de oro absoluta es NUNCA inventar leyes, artículos, resoluciones ni normativas que no estén textualmente en el contexto provisto. Si el contexto provisto está vacío o no contiene información suficiente para justificar la contratación, DEBES responder exactamente con esta frase: 'ADVERTENCIA: No se encontró normativa cargada en el sistema para justificar este proceso.' No completes con conocimiento externo."},
                {"role": "user", "content": prompt_final}
            ]
        )
        
        return JSONResponse(content={
            "argumentacion": respuesta.choices[0].message.content.strip(),
            "archivos_consultados": resultados['metadatas'][0] if resultados.get('metadatas') else []
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})