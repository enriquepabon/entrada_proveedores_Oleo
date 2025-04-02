import os
import sys
import json
import logging
import traceback
from datetime import datetime

# Import your own utility functions directly
import db_utils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('migration.log')
    ]
)
logger = logging.getLogger('migration')

def get_datos_registro_from_file(codigo_guia):
    """
    Get data from a guide's HTML file.
    """
    guias_dir = os.path.join('static', 'guias')
    guia_path = os.path.join(guias_dir, f"guia_{codigo_guia}.html")
    
    if not os.path.exists(guia_path):
        logger.error(f"Guide file not found: {guia_path}")
        return None
    
    try:
        with open(guia_path, 'r') as f:
            content = f.read()
            
        # Try to parse the content as JSON
        try:
            data = json.loads(content)
            logger.info(f"Successfully loaded JSON data for guide: {codigo_guia}")
            return data
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON for guide: {codigo_guia}")
            return None
    except Exception as e:
        logger.error(f"Error reading guide file: {str(e)}")
        return None

def migrate_entry_records():
    """
    Migrate entry records from HTML files to the SQLite database.
    """
    logger.info("Starting migration of entry records...")
    
    # Get path to guias directory
    guias_dir = os.path.join('static', 'guias')
    
    if not os.path.exists(guias_dir):
        logger.error(f"Directory not found: {guias_dir}")
        return False
    
    total_files = 0
    migrated = 0
    errors = 0
    skipped = 0
    
    # Process all guide files
    for filename in os.listdir(guias_dir):
        if filename.startswith('guia_') and filename.endswith('.html'):
            total_files += 1
            codigo_guia = filename.replace('guia_', '').replace('.html', '')
            
            try:
                # Check if record already exists in database
                existing_record = db_utils.get_entry_record_by_guide_code(codigo_guia)
                
                if existing_record:
                    logger.info(f"Record already exists in database, skipping: {codigo_guia}")
                    skipped += 1
                    continue
                
                # Get record data directly from file
                datos = get_datos_registro_from_file(codigo_guia)
                
                if not datos:
                    logger.warning(f"No data found for guide: {codigo_guia}")
                    errors += 1
                    continue
                
                # Create modified_fields JSON if it doesn't exist
                if not datos.get('modified_fields'):
                    modified_fields = {}
                    modified_fields_json = json.dumps(modified_fields)
                    datos['modified_fields'] = modified_fields_json
                elif isinstance(datos.get('modified_fields'), dict):
                    # Convert dict to JSON string
                    datos['modified_fields'] = json.dumps(datos['modified_fields'])
                
                # Ensure all required fields exist
                required_fields = [
                    'codigo_guia', 'codigo_proveedor', 'nombre_proveedor',
                    'fecha_registro', 'hora_registro', 'placa', 'cantidad_racimos'
                ]
                
                for field in required_fields:
                    if field not in datos:
                        datos[field] = ''
                
                # Store in database
                success = db_utils.store_entry_record(datos)
                
                if success:
                    logger.info(f"Successfully migrated record: {codigo_guia}")
                    migrated += 1
                else:
                    logger.error(f"Failed to store record in database: {codigo_guia}")
                    errors += 1
                
            except Exception as e:
                logger.error(f"Error processing guide {codigo_guia}: {str(e)}")
                logger.error(traceback.format_exc())
                errors += 1
    
    logger.info(f"Migration complete. Total files: {total_files}, Migrated: {migrated}, Errors: {errors}, Skipped: {skipped}")
    return True

if __name__ == "__main__":
    logger.info("=== Entry Records Migration Tool ===")
    
    try:
        if migrate_entry_records():
            logger.info("Migration completed successfully!")
            sys.exit(0)
        else:
            logger.error("Migration failed")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1) 