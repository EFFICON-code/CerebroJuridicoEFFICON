import PyPDF2
import re
from dotenv import load_dotenv
import os
from openai import OpenAI
import chromadb
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

load_dotenv()  # Carga la llave secreta del cajón
api_key = os.getenv("OPENAI_API_KEY")  # Usa la llave para abrir la puerta del bibliotecario
client = OpenAI(api_key=api_key)

app = FastAPI()

@app.get("/")
async def root():
    return {"mensaje": "Cerebro Jurídico EFFICON listo"}

def leer_pdf(nombre_archivo):
    with open(nombre_archivo, 'rb') as archivo:
        lector = PyPDF2.PdfReader(archivo)
        texto = ''
        for pagina in lector.pages:
            texto += pagina.extract_text() + '\n'
        return texto

def limpiar_texto(texto):
    texto = re.sub(r'\n\s*\n', '\n\n', texto)
    texto = re.sub(r'\s+', ' ', texto)
    texto = texto.strip()
    return texto

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
    chunks_finales = []
    chunk_temp = ''
    for chunk in chunks:
        if len(chunk_temp) + len(chunk) < tamano_min and chunk_temp:
            chunk_temp += ' ' + chunk
        else:
            if chunk_temp:
                chunks_finales.append(chunk_temp)
            chunk_temp = chunk
    if chunk_temp:
        chunks_finales.append(chunk_temp)
    return chunks_finales

def etiquetar_chunk(chunk):
    prompt = f"""
    Analiza este fragmento de un documento legal y extrae los metadatos exactos en formato simple:
    - Documento: Nombre completo del documento o ley.
    - Tipo: Ley, Reglamento u Ordenanza.
    - Entidad: Quién lo emitió (ej: Asamblea Nacional, Municipio).
    - Área: Tema principal (ej: Educación, Salud, Contratos).
    - Año: Año de publicación o aprobación.
    - Tags: 3-5 palabras clave separadas por comas (ej: contratos, penalidades, derechos).

    Fragmento: {chunk[:500]}  # Solo los primeros 500 para no sobrecargar
    """
    respuesta = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    etiquetas = respuesta.choices[0].message.content.strip()
    return etiquetas

def generar_embedding(chunk):
    respuesta = client.embeddings.create(
        model="text-embedding-3-small",
        input=chunk
    )
    embedding = respuesta.data[0].embedding
    return embedding

def parsear_etiquetas(etiquetas_str):
    metadatos = {}
    for linea in etiquetas_str.split('\n'):
        if ':' in linea:
            clave, valor = linea.split(':', 1)
            metadatos[clave.strip('- ').strip()] = valor.strip()
    return metadatos

@app.post("/procesar_pdf")
async def procesar_pdf(file: UploadFile = File(...)):
    try:
        # Guarda el PDF subido temporalmente
        contents = await file.read()
        with open(file.filename, "wb") as f:
            f.write(contents)
        
        texto_extraido = leer_pdf(file.filename)
        texto_limpiado = limpiar_texto(texto_extraido)
        chunks = trocear_texto(texto_limpiado)
        
        # Crea la biblioteca infinita (en nube, será persistente después)
        db_client = chromadb.PersistentClient(path="/chroma_db")
        coleccion = db_client.get_or_create_collection(name="efficon_juridico")
        
        guardados = []
        for i, chunk in enumerate(chunks):
            etiquetas_str = etiquetar_chunk(chunk)
            embedding = generar_embedding(chunk)
            metadatos = parsear_etiquetas(etiquetas_str)
            metadatos['chunk_id'] = f"chunk_{i+1}"
            coleccion.add(
                documents=[chunk],
                embeddings=[embedding],
                metadatas=[metadatos],
                ids=[f"id_{i+1}"]
            )
            guardados.append(metadatos)
        
        os.remove(file.filename)  # Borra el temporal
        return JSONResponse(content={"mensaje": "PDF procesado y guardado", "metadatos": guardados})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/buscar")
async def buscar(query: str):
    try:
        embedding_pregunta = generar_embedding(query)
        coleccion = db_client.get_collection(name="efficon_juridico")
        resultados = coleccion.query(
            query_embeddings=[embedding_pregunta],
            n_results=5  # Trae 5 resultados más relevantes
        )
        respuesta = []
        for i in range(len(resultados['documents'][0])):
            resultado = {
                "texto": resultados['documents'][0][i],
                "metadatos": resultados['metadatas'][0][i]
            }
            respuesta.append(resultado)
        return JSONResponse(content={"resultados": respuesta})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)