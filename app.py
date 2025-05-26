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

openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    raise RuntimeError("""
    ERROR CRÍTICO: OpenAI API Key no configurada.
    Pasos para solucionar:
    1. Crea un archivo .env con OPENAI_API_KEY=tu_clave
    2. Asegúrate que está en el mismo directorio que app.py
    3. Verifica que el archivo no tenga extensión .txt
    """)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SERVICE_PRICES = {
    "Constitución de empresa": 1500,
    "Defensa laboral": 2000,
    "Consultoría tributaria": 800
}

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

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
        
        content = response.choices[0].message.content
        try:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            json_str = content[json_start:json_end]
            return eval(json_str)
        except:
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
    cotizacion_id = str(uuid.uuid4().fields[-1])[:4]
    numero_cotizacion = f"COT-{datetime.now().year}-{cotizacion_id}"
    
    precio_base = SERVICE_PRICES.get(tipo_servicio, 0)
    
    analisis_ia = analizar_con_ia(descripcion, tipo_servicio)
    
    precio_final = precio_base * (1 + analisis_ia['ajuste_precio'] / 100)
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO cotizaciones (numero_cotizacion, nombre_cliente, email, tipo_servicio, descripcion, precio, fecha) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (numero_cotizacion, nombre_cliente, email, tipo_servicio, descripcion, precio_final, fecha_actual)
    )
    conn.commit()
    conn.close()
    
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
