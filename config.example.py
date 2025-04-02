# Example configuration file for TiquetesApp
# Copy this file to config.py and update with your actual values

# Server configuration
CONFIG_HOST = 'localhost'
CONFIG_PORT = '8082'

# Roboflow API configuration
# Sign up at https://app.roboflow.com to get these values
ROBOFLOW_API_KEY = 'YOUR_API_KEY_HERE'  # Get this from your Roboflow account
ROBOFLOW_WORKSPACE = 'oleoflores'       # Your Roboflow workspace name
ROBOFLOW_PROJECT = 'clasificacion-racimos'  # Your project name
ROBOFLOW_VERSION = '1'                  # The model version to use

# Other configuration options
DEBUG = True
SECRET_KEY = 'generate-a-secure-key-here' 