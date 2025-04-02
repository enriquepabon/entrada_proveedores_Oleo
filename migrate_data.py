import sqlite3
import pymysql
from config import Config
from app import app

def migrate_data():
    if not app.config['IS_PRODUCTION']:
        print("Este script debe ejecutarse en producción")
        return
    
    # Conectar a SQLite
    sqlite_conn = sqlite3.connect('tiquetes.db')
    sqlite_cursor = sqlite_conn.cursor()
    
    # Conectar a MySQL
    mysql_conn = pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB']
    )
    mysql_cursor = mysql_conn.cursor()
    
    # Migrar datos de cada tabla
    # ... código de migración ...

if __name__ == "__main__":
    migrate_data() 