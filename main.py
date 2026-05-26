from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from typing import Optional, List

app = FastAPI(title="Dann-Alpes Reviews API")

# Conexión a MongoDB
client = MongoClient("mongodb+srv://admin_sara:Saris3011@cluster0.rrzrclg.mongodb.net/?appName=Cluster0")
db = client["dann_alpes_db"]
reviews_collection = db["reviews"]

# --- MODELOS PYDANTIC ---
class ReviewCreate(BaseModel):
    hotel_id: str
    cliente_id: str
    reserva_id: str
    calificacion: int
    texto: str

class ReviewEdit(BaseModel):
    calificacion: int
    texto: str

class AdminResponse(BaseModel):
    respuesta_admin: str

# --- REQUERIMIENTOS FUNCIONALES (CLIENTES) ---

# RF1: Crear reseña [cite: 32, 33, 34]
@app.post("/api/reviews/")
async def crear_resena(review: ReviewCreate):
    # Validar que no haya reseñado la misma reserva antes
    if reviews_collection.find_one({"reserva_id": review.reserva_id}):
        raise HTTPException(status_code=400, detail="Ya existe una reseña para esta reserva")

    nueva_resena = {
        "hotel_id": review.hotel_id,
        "cliente_id": review.cliente_id,
        "reserva_id": review.reserva_id,
        "calificacion": review.calificacion,
        "texto": review.texto,
        "fecha_creacion": datetime.now(),
        "utilidad": 0,
        "estado": "publicada", # Puede ser "publicada" o "eliminada" [cite: 45]
        "respuesta_admin": None,
        "destacada": False
    }
    resultado = reviews_collection.insert_one(nueva_resena)
    return {"message": "Reseña creada", "id": str(resultado.inserted_id)}

# RF2: Editar reseña [cite: 35, 36]
@app.put("/api/reviews/{review_id}")
async def editar_resena(review_id: str, review: ReviewEdit):
    resultado = reviews_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$set": {"calificacion": review.calificacion, "texto": review.texto}}
    )
    if resultado.modified_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada o sin cambios")
    return {"message": "Reseña actualizada"}

# RF3: Eliminar reseña (Soft delete) [cite: 37, 38]
@app.delete("/api/reviews/{review_id}/cliente")
async def eliminar_resena_cliente(review_id: str):
    # Usamos soft-delete cambiando el estado a "eliminada" como pide el RF6 [cite: 45]
    resultado = reviews_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$set": {"estado": "eliminada"}}
    )
    return {"message": "Reseña eliminada por el cliente"}

# RF4: Consultar reseñas de un hotel (Público) [cite: 39, 40, 41]
@app.get("/api/hotels/{hotel_id}/reviews")
async def consultar_resenas_hotel(hotel_id: str, sort_by: str = "fecha", skip: int = 0, limit: int = 10):
    sort_field = "fecha_creacion" if sort_by == "fecha" else "utilidad"
    
    # Primero buscamos si hay una destacada para ponerla al tope [cite: 54]
    destacada = list(reviews_collection.find(
        {"hotel_id": hotel_id, "estado": "publicada", "destacada": True}, {"_id": 0}
    ))
    
    # Luego buscamos el resto, excluyendo la destacada si existe
    query = {"hotel_id": hotel_id, "estado": "publicada", "destacada": False}
    cursor = reviews_collection.find(query, {"_id": 0}).sort(sort_field, -1).skip(skip).limit(limit)
    
    return destacada + list(cursor)

# RF5: Marcar reseña como útil [cite: 42, 43]
@app.patch("/api/reviews/{review_id}/util")
async def votar_utilidad(review_id: str):
    reviews_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$inc": {"utilidad": 1}}
    )
    return {"message": "Voto registrado"}

# RF6: Consultar historial de reseñas propias [cite: 44, 45, 46]
@app.get("/api/clientes/{cliente_id}/reviews")
async def historial_cliente(cliente_id: str, sort_by: str = "fecha"):
    sort_field = "fecha_creacion" if sort_by == "fecha" else "hotel_id"
    cursor = reviews_collection.find(
        {"cliente_id": cliente_id},
        {"_id": 0}
    ).sort(sort_field, -1)
    return list(cursor)

# --- REQUERIMIENTOS FUNCIONALES (ADMINISTRADOR) ---

# RF7: Responder reseña [cite: 48, 49]
@app.patch("/api/reviews/{review_id}/respuesta")
async def responder_resena(review_id: str, admin_resp: AdminResponse):
    reviews_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$set": {"respuesta_admin": admin_resp.respuesta_admin}}
    )
    return {"message": "Respuesta guardada"}

# RF8: Eliminar reseña por moderación [cite: 50, 51]
@app.delete("/api/reviews/{review_id}/admin")
async def eliminar_resena_admin(review_id: str):
    reviews_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$set": {"estado": "eliminada_por_admin"}}
    )
    return {"message": "Reseña eliminada por moderación"}

# RF9: Destacar reseña [cite: 53, 54, 55]
@app.patch("/api/reviews/{review_id}/destacar")
async def destacar_resena(review_id: str, hotel_id: str):
    # Quitar el destacado de cualquier otra reseña del mismo hotel [cite: 55]
    reviews_collection.update_many(
        {"hotel_id": hotel_id, "destacada": True},
        {"$set": {"destacada": False}}
    )
    # Destacar la nueva
    reviews_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$set": {"destacada": True}}
    )
    return {"message": "Reseña destacada exitosamente"}

# --- REQUERIMIENTOS DE CONSULTA (RFC) ---

# RFC1: Top 10 hoteles por calificación [cite: 57, 58]
@app.get("/api/stats/top-hoteles")
async def top_hoteles(fecha_inicio: datetime, fecha_fin: datetime):
    pipeline = [
        {"$match": {"estado": "publicada", "fecha_creacion": {"$gte": fecha_inicio, "$lte": fecha_fin}}},
        {"$group": {"_id": "$hotel_id", "promedio_calificacion": {"$avg": "$calificacion"}}},
        {"$sort": {"promedio_calificacion": -1}},
        {"$limit": 10}
    ]
    return list(reviews_collection.aggregate(pipeline))

# RFC2: Evolución de la reputación de un hotel en el tiempo [cite: 59, 60]
@app.get("/api/stats/evolucion/{hotel_id}")
async def evolucion_hotel(hotel_id: str, year: int):
    pipeline = [
        {"$match": {
            "hotel_id": hotel_id, 
            "estado": "publicada",
            "$expr": {"$eq": [{"$year": "$fecha_creacion"}, year]}
        }},
        {"$group": {
            "_id": {"mes": {"$month": "$fecha_creacion"}},
            "promedio_calificacion": {"$avg": "$calificacion"}
        }},
        {"$sort": {"_id.mes": 1}}
    ]
    return list(reviews_collection.aggregate(pipeline))

# RFC3: Perfil comparativo de hoteles por ciudad [cite: 61, 62]
# Nota: Como la ciudad está en Oracle, APEX debe enviar la lista de hotel_ids que pertenecen a esa ciudad
@app.post("/api/stats/comparativo-ciudad")
async def comparativo_ciudad(hoteles_id: List[str]):
    pipeline = [
        {"$match": {"hotel_id": {"$in": hoteles_id}, "estado": "publicada"}},
        {"$group": {
            "_id": "$hotel_id",
            "promedio_calificacion": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1},
            "con_respuesta": {"$sum": {"$cond": [{"$ne": ["$respuesta_admin", None]}, 1, 0]}},
            "destacadas": {"$sum": {"$cond": ["$destacada", 1, 0]}}
        }},
        {"$project": {
            "hotel_id": "$_id",
            "promedio_calificacion": 1,
            "total_resenas": 1,
            "porcentaje_respuesta": {"$multiply": [{"$divide": ["$con_respuesta", "$total_resenas"]}, 100]},
            "porcentaje_destacadas": {"$multiply": [{"$divide": ["$destacadas", "$total_resenas"]}, 100]}
        }}
    ]
    return list(reviews_collection.aggregate(pipeline))