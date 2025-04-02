#!/usr/bin/env python3
"""
Script para verificar y corregir URLs en plantillas HTML.
Busca patrones de url_for sin prefijos de blueprint y los corrige.
"""
import os
import re
import glob
import argparse

# Mapeo de endpoints a blueprints correctos
URL_MAPPINGS = {
    # Endpoints de entrada
    'home': 'entrada.home',
    'index': 'entrada.index',
    'processing': 'entrada.processing',
    'review': 'entrada.review',
    'register': 'entrada.register',
    'review_pdf': 'entrada.review_pdf',
    'lista_registros_entrada': 'entrada.lista_registros_entrada',
    'ver_registro_entrada': 'entrada.ver_registro_entrada',
    'update_data': 'entrada.update_data',
    'process_image': 'entrada.process_image',
    'processing_screen': 'entrada.processing_screen',
    'generar_pdf_registro': 'entrada.generar_pdf_registro',
    
    # Endpoints de pesaje
    'pesaje': 'pesaje.pesaje',
    'pesaje_inicial': 'pesaje.pesaje_inicial',
    'pesaje_tara': 'pesaje.pesaje_tara',
    'lista_pesajes': 'pesaje.lista_pesajes',
    'lista_pesajes_neto': 'pesaje.lista_pesajes_neto',
    'procesar_pesaje_directo': 'pesaje.procesar_pesaje_directo',
    'procesar_pesaje_tara_directo': 'pesaje.procesar_pesaje_tara_directo',
    'pesaje_neto': 'pesaje.pesaje_neto',
    'registrar_peso_directo': 'pesaje.registrar_peso_directo',
    'registrar_peso_virtual': 'pesaje.registrar_peso_virtual',
    'registrar_peso_neto': 'pesaje.registrar_peso_neto',
    'registrar_peso_neto_directo': 'pesaje.registrar_peso_neto_directo',
    'registrar_peso_neto_virtual': 'pesaje.registrar_peso_neto_virtual',
    
    # Endpoints de clasificación
    'clasificacion': 'clasificacion.clasificacion',
    'registrar_clasificacion': 'clasificacion.registrar_clasificacion',
    'listar_clasificaciones': 'clasificacion.listar_clasificaciones',
    'listar_clasificaciones_filtradas': 'clasificacion.listar_clasificaciones_filtradas',
    'ver_resultados_clasificacion': 'clasificacion.ver_resultados_clasificacion',
    'procesar_clasificacion': 'clasificacion.procesar_clasificacion',
    'procesar_clasificacion_manual': 'clasificacion.procesar_clasificacion_manual',
    'iniciar_procesamiento': 'clasificacion.iniciar_procesamiento',
    'check_procesamiento_status': 'clasificacion.check_procesamiento_status',
    'procesar_imagenes': 'clasificacion.procesar_imagenes',
    'mostrar_resultados_automaticos': 'clasificacion.mostrar_resultados_automaticos',
    
    # Endpoints misc
    'upload_file': 'misc.upload_file',
    'serve_guia': 'misc.serve_guia',
    'revalidation_results': 'misc.revalidation_results',
    'revalidation_success': 'misc.revalidation_success',
    'ver_resultados_pesaje': 'misc.ver_resultados_pesaje',
    'reprocess_plate': 'misc.reprocess_plate',
    
    # Endpoints de salida
    'registro_salida': 'salida.registro_salida',
    'completar_registro_salida': 'salida.completar_registro_salida',
    'ver_resultados_salida': 'salida.ver_resultados_salida',
    
    # Endpoints de pesaje_neto
    'ver_resultados_pesaje_neto': 'pesaje_neto.ver_resultados_pesaje_neto',
    
    # Endpoints de admin
    'migrar_registros': 'admin.migrar_registros',
    
    # Endpoints de API
    'test_webhook': 'api.test_webhook',
    'test_revalidation': 'api.test_revalidation',
    'verificar_placa': 'api.verificar_placa',
}

def find_template_files(template_dir="templates", extension=".html"):
    """
    Encuentra todos los archivos de plantilla en el directorio especificado.
    """
    return glob.glob(os.path.join(template_dir, f"**/*{extension}"), recursive=True)

def find_url_patterns(content):
    """
    Encuentra patrones de url_for en el contenido.
    """
    # Patrón para buscar url_for con comillas simples o dobles
    pattern = r"url_for\(['\"]([\w.]+)['\"]"
    return re.finditer(pattern, content)

def check_file(filepath, fix=False, verbose=False):
    """
    Verifica un archivo en busca de patrones url_for y los corrige si fix=True.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    matches = list(find_url_patterns(content))
    
    if not matches:
        if verbose:
            print(f"No se encontraron patrones url_for en {filepath}")
        return 0
    
    changes = []
    modified_content = content
    
    for match in matches:
        endpoint = match.group(1)
        
        # Si el endpoint ya tiene un punto (blueprint.endpoint), asumimos que está correcto
        if '.' in endpoint:
            continue
            
        # Si el endpoint está en nuestro mapeo, lo reemplazamos
        if endpoint in URL_MAPPINGS:
            corrected_endpoint = URL_MAPPINGS[endpoint]
            
            # Reemplazamos el endpoint en el contenido
            change_from = f"url_for('{endpoint}')"
            change_to = f"url_for('{corrected_endpoint}')"
            
            # También maneja comillas dobles
            if change_from not in modified_content:
                change_from = f'url_for("{endpoint}")'
                change_to = f'url_for("{corrected_endpoint}")'
                
            changes.append((change_from, change_to))
            modified_content = modified_content.replace(change_from, change_to)
            
            if verbose:
                print(f"  Encontrado: {change_from} -> {change_to}")
    
    # Si hay cambios y fix=True, guardamos el archivo modificado
    if changes and fix:
        # Crear una copia de respaldo
        backup_path = f"{filepath}.bak_url"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        # Guardar el archivo modificado
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(modified_content)
            
        print(f"✓ Corregido {filepath} ({len(changes)} cambios)")
    elif changes:
        print(f"! Se encontraron {len(changes)} posibles correcciones en {filepath}")
        
    return len(changes)

def main():
    parser = argparse.ArgumentParser(description='Verifica y corrige URLs en plantillas')
    parser.add_argument('--fix', action='store_true', help='Corregir automáticamente los problemas encontrados')
    parser.add_argument('--verbose', action='store_true', help='Mostrar información detallada')
    args = parser.parse_args()
    
    template_files = find_template_files()
    
    print(f"Analizando {len(template_files)} archivos de plantilla...")
    
    total_files = 0
    total_changes = 0
    
    for filepath in template_files:
        changes = check_file(filepath, fix=args.fix, verbose=args.verbose)
        if changes > 0:
            total_files += 1
            total_changes += changes
    
    print(f"\nResumen:")
    print(f"  - Archivos analizados: {len(template_files)}")
    print(f"  - Archivos con problemas: {total_files}")
    print(f"  - Total de problemas encontrados: {total_changes}")
    
    if args.fix:
        print(f"  - Problemas corregidos: {total_changes}")
    else:
        print(f"\nEjecuta con --fix para corregir los problemas automáticamente.")

if __name__ == "__main__":
    main() 