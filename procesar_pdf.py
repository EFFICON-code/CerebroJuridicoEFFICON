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
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
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
async def procesar_pdf(file: UploadFile = File(...), entidad: str = Form("General")):
    try:
        ruta_temp = f"temp_{file.filename}"
        contents = await file.read()
        with open(ruta_temp, "wb") as f:
            f.write(contents)
        
        texto_extraido = leer_pdf(ruta_temp)
        texto_limpiado = limpiar_texto(texto_extraido)
        chunks = trocear_texto(texto_limpiado)
        
        db_client = chromadb.PersistentClient(path="./chroma_db_juridico")
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
        db_client = chromadb.PersistentClient(path="./chroma_db_juridico")
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
        
        # 1. Búsqueda Vectorial
        embedding_pregunta = generar_embedding(texto_busqueda)
        db_client = chromadb.PersistentClient(path="./chroma_db_juridico")
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        filtro = {}
        if entidad_filtro != "TODAS":
            filtro = {"entidad": entidad_filtro.strip().upper()}
            
        resultados = coleccion.query(
            query_embeddings=[embedding_pregunta],
            n_results=7,
            where=filtro if filtro else None
        )
        
        # 2. Ensamblar Contexto
        textos_legales = ""
        if resultados and resultados['documents'] and resultados['documents'][0]:
            for i in range(len(resultados['documents'][0])):
                archivo = resultados['metadatas'][0][i].get('archivo', 'Normativa')
                textos_legales += f"\n--- EXTRAÍDO DE: {archivo} ---\n{resultados['documents'][0][i]}\n"
        
        # 3. Inyección en el Prompt
        if "{{Contexto_Legal_ChromaDB}}" in prompt_completo:
            prompt_final = prompt_completo.replace("{{Contexto_Legal_ChromaDB}}", textos_legales)
        else:
            prompt_final = f"{prompt_completo}\n\nCONTEXTO LEGAL ESTRICTO:\n{textos_legales}"
            
        # 4. Prompt de Sistema (El Fallback Elegante)
        instruccion_sistema = """
        Eres un abogado experto en contratación pública en Ecuador. Redactas informes de necesidad para instituciones del Estado.
        Regla 1: Basa tu argumentación en el CONTEXTO LEGAL ESTRICTO provisto.
        Regla 2: Si el contexto legal está vacío o es insuficiente para justificar el objeto de contratación, redacta la justificación en los mismos 3 párrafos formales, pero basándote en los principios generales del derecho administrativo ecuatoriano (eficiencia, eficacia, necesidad pública, servicio a la comunidad) y la misión general de la entidad. Utiliza un lenguaje institucional impecable.
        Regla 3: NUNCA, bajo ninguna circunstancia, insertes advertencias, notas de error, ni frases como 'no encontré información', 'no hay artículos' o 'el contexto no menciona'. El texto resultante irá impreso directamente en un informe oficial y debe lucir siempre como una redacción jurídica perfecta y terminada.
        """

        respuesta = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1, # Muy bajo para evitar desvaríos, pero permite redactar fluidamente
            messages=[
                {"role": "system", "content": instruccion_sistema},
                {"role": "user", "content": prompt_final}
            ]
        )
        
        return JSONResponse(content={
            "argumentacion": respuesta.choices[0].message.content.strip(),
            "archivos_consultados": resultados['metadatas'][0] if resultados.get('metadatas') else []
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)