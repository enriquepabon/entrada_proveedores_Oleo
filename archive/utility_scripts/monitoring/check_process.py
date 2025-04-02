#!/usr/bin/env python3
import time
import requests
import sys

def main():
    """Check the status of a classification process until it completes."""
    if len(sys.argv) < 2:
        print("Usage: python check_process.py <codigo_guia>")
        return
    
    codigo_guia = sys.argv[1]
    base_url = "http://localhost:8082/clasificacion/check_procesamiento_status/"
    url = f"{base_url}{codigo_guia}"
    
    print(f"Checking process status for {codigo_guia}...")
    
    while True:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                progress = data.get("progress", 0)
                message = data.get("message", "No message")
                
                print(f"Status: {status}, Progress: {progress}%, Message: {message}")
                
                if status == "completed":
                    print("Processing completed!")
                    print(f"Redirect URL: {data.get('redirect_url', 'None')}")
                    break
            else:
                print(f"Error: Status code {response.status_code}")
                break
        except Exception as e:
            print(f"Error checking status: {e}")
            break
        
        time.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    main() 