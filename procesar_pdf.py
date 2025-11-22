import PyPDF2
import re
from dotenv import load_dotenv
import os
from openai import OpenAI
import chromadb

load_dotenv()  # Carga la llave secreta del cajón
api_key = os.getenv("OPENAI_API_KEY")  # Usa la llave para abrir la puerta del bibliotecario
client = OpenAI(api_key=api_key)

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

# Prueba: Cambia 'ejemplo.pdf' por el nombre de tu PDF si es diferente
texto_extraido = leer_pdf('ejemplo.pdf')
texto_limpiado = limpiar_texto(texto_extraido)
chunks = trocear_texto(texto_limpiado)

# Crea la biblioteca infinita local
db_client = chromadb.Client()
coleccion = db_client.get_or_create_collection(name="efficon_juridico")

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
    print(f"Guardado chunk {i+1} con metadatos: {metadatos}")

print("Todo guardado en la biblioteca infinita local.")
# Prueba de búsqueda: Cambia la pregunta si quieres
pregunta = "contratos públicos en Ecuador"  # Ejemplo de búsqueda
embedding_pregunta = generar_embedding(pregunta)
resultados = coleccion.query(
    query_embeddings=[embedding_pregunta],
    n_results=3  # Trae los 3 pedazos más relevantes
)
print("Resultados de búsqueda:")
for i, doc in enumerate(resultados['documents'][0]):
    print(f"Resultado {i+1}:")
    print(doc)
    print("Metadatos:", resultados['metadatas'][0][i])
    print("\n")