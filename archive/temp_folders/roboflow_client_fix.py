







class DirectRoboflowClient:
    """Cliente alternativo que usa requests directamente para hablar con la API de Roboflow"""
    
    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        logger.info(f"Inicializado cliente directo de Roboflow para {api_url}")
        
    def run_workflow(self, workspace_name, workflow_id, images, use_cache=True):
        """
        Ejecuta un workflow de Roboflow usando solicitudes HTTP directas.
        Compatible con la interfaz del SDK oficial.
        """
        image_path = images.get("image")
        logger.info(f"Ejecutando workflow {workflow_id} con imagen {image_path}")
        
        workflow_url = f"https://detect.roboflow.com/infer/workflows/{workspace_name}/{workflow_id}"
        
        # Si la imagen es un archivo local, primero vamos a verificar su tamaño
        if os.path.exists(image_path):
            try:
                # Abrir la imagen y verificar su tamaño
                with Image.open(image_path) as img:
                    width, height = img.size
                    logger.info(f"Imagen original: {width}x{height} pixels")
                    
                    # Tamaño máximo permitido por Roboflow
                    max_width = 1152
                    max_height = 2048
                    
                    # Verificar si la imagen necesita ser redimensionada
                    if width > max_width or height > max_height:
                        logger.info(f"La imagen excede el tamaño máximo permitido por Roboflow. Redimensionando...")
                        # Calcular ratio para mantener proporciones
                        ratio = min(max_width/width, max_height/height)
                        new_size = (int(width * ratio), int(height * ratio))
                        
                        # Crear un archivo temporal para la imagen redimensionada
                        resized_image_path = image_path.replace('.jpg', '_resized.jpg')
                        if not resized_image_path.endswith('.jpg'):
                            resized_image_path += '_resized.jpg'
                        
                        # Redimensionar y guardar
                        resized_img = img.resize(new_size, Image.LANCZOS)
                        resized_img.save(resized_image_path, "JPEG", quality=95)
                        logger.info(f"Imagen redimensionada guardada en: {resized_image_path}")
                        
                        # Usar la imagen redimensionada en lugar de la original
                        image_path = resized_image_path
            except Exception as e:
                logger.error(f"Error al procesar la imagen: {str(e)}")
                logger.error(traceback.format_exc())
                # Continuar con la imagen original si hay error en el redimensionamiento
            
            # Codificar la imagen en base64 para enviar a Roboflow
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode("utf-8")
                
            payload = {
                "api_key": self.api_key,
                "inputs": {
                    "image": {"type": "base64", "value": image_data}
                }
            }
        else:
            # Si es una URL, usar ese formato
            payload = {
                "api_key": self.api_key,
                "inputs": {
                    "image": {"type": "url", "value": image_path}
                }
            }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Enviando solicitud HTTP a {workflow_url}")
            response = requests.post(
                workflow_url, 
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Respuesta recibida correctamente de Roboflow")
                return result
