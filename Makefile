# Makefile para el proyecto TiquetesApp

.PHONY: run clean-temp clean-redundant fix-templates check-db install-deps help

# Variables
PYTHON = python3
PIP = $(PYTHON) -m pip

# Comandos principales
help:
	@echo "Comandos disponibles:"
	@echo "  make run              - Ejecutar la aplicación"
	@echo "  make clean-temp       - Limpiar archivos temporales (.pyc, __pycache__, etc.)"
	@echo "  make clean-redundant  - Limpiar archivos redundantes (backup, respaldos, archivos antiguos)"
	@echo "  make fix-templates    - Corregir URLs en las plantillas HTML"
	@echo "  make check-db         - Verificar la integridad de la base de datos"
	@echo "  make install-deps     - Instalar dependencias del proyecto"

run:
	$(PYTHON) run.py

clean-temp:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".DS_Store" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name ".tox" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	@echo "Archivos temporales eliminados"

clean-redundant:
	$(PYTHON) scripts/clean_redundant_files.py --delete
	@echo "Archivos redundantes eliminados"

fix-templates:
	$(PYTHON) scripts/fix_template_urls.py --fix
	@echo "URLs en plantillas corregidas"

check-db:
	$(PYTHON) -c "from app import app; from db_schema import Base; from sqlalchemy import create_engine; engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI']); Base.metadata.create_all(engine); print('Base de datos verificada correctamente')"

install-deps:
	$(PIP) install -r requirements.txt
	@echo "Dependencias instaladas correctamente" 