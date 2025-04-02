# Archive Directory

This directory contains older versions of files and code that have been migrated to the new blueprint-based structure. These files are kept for reference but are not part of the active codebase.

## Directory Structure

- **old_app/**: Contains the original monolithic application files
  - `apptiquetes.py`: The original main application file
  - `utils.py`: The original utilities file
  - Other legacy application files

- **migration_backups/**: Contains migration attempts and backup directories
  - `blueprint_migration_*`: Different attempts at migrating to blueprints
  - `migration_work_*`: Working directories during migration
  - `utils_migration_*`: Utility migration files

- **TiquetesApp_backup/**: Complete backup of the app at an earlier state

- **bak_files/**: Various .bak files created during migration and refactoring

## Purpose

These files are maintained for:
1. Historical reference
2. Recovering code if needed
3. Understanding the development journey of the application

**Note**: The current active codebase uses the Flask blueprint structure in the `/app` directory. Refer to `estructura_proyecto_actual.md` for details on the current structure. 