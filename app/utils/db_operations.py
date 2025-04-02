def get_entry_records(codigo_guia=None):
    """
    Busca registros de entrada por código de guía específico o según filtros.
    Esta función prioriza la búsqueda por código de guía exacto para evitar
    mezclar datos entre diferentes entregas del mismo proveedor.
    
    Args:
        codigo_guia (str, optional): Código de guía específico a buscar
        
    Returns:
        list: Lista de registros de entrada encontrados
    """
    try:
        import sqlite3
        import logging
        logger = logging.getLogger(__name__)
        
        # Buscar en ambas bases de datos
        dbs = ['database.db', 'tiquetes.db']
        registros = []
        
        for db_path in dbs:
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Verificar si la tabla entry_records existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
                if not cursor.fetchone():
                    logger.warning(f"Tabla entry_records no encontrada en {db_path}")
                    continue
                
                # Definir la consulta según si se busca por código específico o filtros
                if codigo_guia:
                    cursor.execute("SELECT * FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
                else:
                    # Si no hay código específico, retornar vacío para evitar mezclar datos
                    logger.warning("Se requiere código de guía específico para buscar registros de entrada")
                    continue
                
                # Convertir resultados a diccionarios
                for row in cursor.fetchall():
                    entry = {key: row[key] for key in row.keys()}
                    registros.append(entry)
                    logger.info(f"Encontrado registro de entrada para {codigo_guia} en {db_path}")
                
                conn.close()
                
                # Si encontramos registros, no necesitamos buscar en la otra base de datos
                if registros:
                    break
            except Exception as e:
                logger.error(f"Error consultando {db_path}: {str(e)}")
                if 'conn' in locals():
                    conn.close()
        
        return registros
    except Exception as e:
        logger.error(f"Error general en get_entry_records: {str(e)}")
        return []

def update_pesaje_bruto(codigo_guia, datos):
    """
    Actualiza un registro de pesaje bruto existente.
    
    Args:
        codigo_guia (str): Código de guía a actualizar
        datos (dict): Datos para actualizar
        
    Returns:
        bool: True si se actualizó correctamente, False en caso contrario
    """
    try:
        import sqlite3
        import logging
        logger = logging.getLogger(__name__)
        
        # Buscar en ambas bases de datos
        dbs = ['database.db', 'tiquetes.db']
        actualizado = False
        
        for db_path in dbs:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Verificar si la tabla pesajes_bruto existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'")
                if not cursor.fetchone():
                    logger.warning(f"Tabla pesajes_bruto no encontrada en {db_path}")
                    continue
                
                # Verificar si existe el registro
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia = ?", (codigo_guia,))
                if not cursor.fetchone():
                    logger.warning(f"No se encontró registro para {codigo_guia} en {db_path}")
                    continue
                
                # Construir sentencia UPDATE
                columns = []
                values = []
                
                for key, value in datos.items():
                    columns.append(f"{key} = ?")
                    values.append(value)
                
                # Añadir el código de guía para la condición WHERE
                values.append(codigo_guia)
                
                # Ejecutar UPDATE
                update_query = f"UPDATE pesajes_bruto SET {', '.join(columns)} WHERE codigo_guia = ?"
                cursor.execute(update_query, values)
                conn.commit()
                
                logger.info(f"Registro actualizado para {codigo_guia} en {db_path}")
                actualizado = True
                
                conn.close()
            except Exception as e:
                logger.error(f"Error actualizando en {db_path}: {str(e)}")
                if 'conn' in locals():
                    conn.close()
        
        return actualizado
    except Exception as e:
        logger.error(f"Error general en update_pesaje_bruto: {str(e)}")
        return False 