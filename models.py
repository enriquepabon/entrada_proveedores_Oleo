from db_schema import db
from datetime import datetime

class EntryRecord(db.Model):
    __tablename__ = 'entry_records'
    id = db.Column(db.Integer, primary_key=True)
    codigo_guia = db.Column(db.String(50), unique=True, nullable=False)
    codigo_proveedor = db.Column(db.String(50))
    nombre_proveedor = db.Column(db.String(100))
    fecha_registro = db.Column(db.String(20))
    hora_registro = db.Column(db.String(20))
    image_filename = db.Column(db.String(200))
    plate_image_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Agrega los demás modelos aquí... 