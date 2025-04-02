import os
import time
import sys

def main():
    """
    Simple script to monitor the Flask application's error logs.
    """
    # Define log file paths to check
    log_files = [
        'flask_app.log',
        os.path.join('app', 'flask_app.log'),
        os.path.join('logs', 'flask_app.log'),
        os.path.join('app', 'logs', 'flask_app.log')
    ]
    
    # Find the first existing log file
    log_file = None
    for file_path in log_files:
        if os.path.exists(file_path):
            log_file = file_path
            break
    
    if not log_file:
        print("No log file found in the expected locations.")
        return
    
    print(f"Monitoring log file: {log_file}")
    
    # Get the file size
    file_size = os.path.getsize(log_file)
    
    # Open the file and read it
    with open(log_file, 'r') as f:
        # Move to the end of the file
        f.seek(file_size)
        
        # Keep checking for new content
        try:
            while True:
                line = f.readline()
                if line:
                    # Filter for relevant content
                    if "Roboflow" in line or "ERROR:" in line or "procesamiento" in line or "clasificacion" in line:
                        print(line.strip())
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopped monitoring logs.")

if __name__ == "__main__":
    main() 