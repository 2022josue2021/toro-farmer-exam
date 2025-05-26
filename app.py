from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import uuid
import openai
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 2. Configurar OpenAI inmediatamente después
openai.api_key = os.getenv("OPENAI_API_KEY")

# 3. Verificación EXPLÍCITA
if not openai.api_key:
    raise RuntimeError("""
    ERROR CRÍTICO: OpenAI API Key no configurada.
    Pasos para solucionar:
    1. Crea un archivo .env con OPENAI_API_KEY=tu_clave
    2. Asegúrate que está en el mismo directorio que app.py
    3. Verifica que el archivo no tenga extensión .txt
    """)

# 4. Solo después inicializar FastAPI
app = FastAPI()

# Configuración de archivos estáticos y templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Precios de los servicios
SERVICE_PRICES = {
    "Constitución de empresa": 1500,
    "Defensa laboral": 2000,
    "Consultoría tributaria": 800
}

# Conexión a la base de datos SQLite
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Crear tabla si no existe
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_cotizacion TEXT NOT NULL,
            nombre_cliente TEXT NOT NULL,
            email TEXT NOT NULL,
            tipo_servicio TEXT NOT NULL,
            descripcion TEXT,
            precio REAL NOT NULL,
            fecha TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()
@app.get("/api/cotizaciones")
async def obtener_cotizaciones():
    conn = get_db_connection()
    cotizaciones = conn.execute(
        "SELECT * FROM cotizaciones ORDER BY fecha DESC"
    ).fetchall()
    conn.close()
    
    # Convertir Row objects a diccionarios
    result = []
    for row in cotizaciones:
        result.append({
            "numero_cotizacion": row["numero_cotizacion"],
            "nombre_cliente": row["nombre_cliente"],
            "email": row["email"],
            "tipo_servicio": row["tipo_servicio"],
            "descripcion": row["descripcion"],
            "precio": row["precio"],
            "fecha": row["fecha"]
        })
    
    return result
    
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def analizar_con_ia(descripcion, tipo_servicio):
    try:
        # Verifica que la descripción no esté vacía
        if not descripcion.strip():
            raise ValueError("Descripción vacía")
        
        prompt = f"""
        Eres un experto en servicios legales. Analiza este caso:
        
        **Tipo de Servicio**: {tipo_servicio}
        **Descripción del Caso**: {descripcion}
        
        Proporciona un análisis en formato JSON con estas claves:
        1. "complejidad" (Baja/Media/Alta)
        2. "ajuste_precio" (0, 25 o 50)
        3. "servicios_adicionales" (lista)
        4. "propuesta_texto" (2-3 párrafos profesionales)
        
        La propuesta debe incluir:
        - Servicios incluidos
        - Tiempo estimado
        - Condiciones básicas
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente legal que genera cotizaciones profesionales."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # Parsear la respuesta correctamente
        content = response.choices[0].message.content
        try:
            # Intenta extraer el JSON si la respuesta lo contiene
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            json_str = content[json_start:json_end]
            return eval(json_str)
        except:
            # Si falla, devuelve un formato estándar con la respuesta completa
            return {
                'complejidad': 'Media',
                'ajuste_precio': 0,
                'servicios_adicionales': [],
                'propuesta_texto': content if content else "Propuesta generada por IA"
            }
            
    except Exception as e:
        print(f"Error en analizar_con_ia: {str(e)}")
        return {
            'complejidad': 'Media',
            'ajuste_precio': 0,
            'servicios_adicionales': [],
            'propuesta_texto': f"Error al generar propuesta: {str(e)}"
        }
        
@app.post("/generar-cotizacion")
async def generar_cotizacion(
    nombre_cliente: str = Form(...),
    email: str = Form(...),
    tipo_servicio: str = Form(...),
    descripcion: str = Form(...)
):
    # Generar número de cotización único
    cotizacion_id = str(uuid.uuid4().fields[-1])[:4]
    numero_cotizacion = f"COT-{datetime.now().year}-{cotizacion_id}"
    
    # Obtener precio base según servicio
    precio_base = SERVICE_PRICES.get(tipo_servicio, 0)
    
    # Analizar con IA
    analisis_ia = analizar_con_ia(descripcion, tipo_servicio)
    
    # Aplicar ajuste de precio
    precio_final = precio_base * (1 + analisis_ia['ajuste_precio'] / 100)
    
    # Fecha actual
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Guardar en base de datos
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO cotizaciones (numero_cotizacion, nombre_cliente, email, tipo_servicio, descripcion, precio, fecha) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (numero_cotizacion, nombre_cliente, email, tipo_servicio, descripcion, precio_final, fecha_actual)
    )
    conn.commit()
    conn.close()
    
    # Retornar respuesta JSON
    return JSONResponse({
        "numero_cotizacion": numero_cotizacion,
        "nombre_cliente": nombre_cliente,
        "email": email,
        "tipo_servicio": tipo_servicio,
        "descripcion": descripcion,
        "precio_base": precio_base,
        "precio_final": precio_final,
        "fecha": fecha_actual,
        "analisis_ia": analisis_ia
    })

    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)