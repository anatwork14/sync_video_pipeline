import subprocess
import re
import sys
import time

def main():
    print("Starting LocalTunnel...")
    
    # Check if npx is available
    try:
        subprocess.run(["npx", "--version"], capture_output=True, check=True)
    except Exception:
        print(" ❌ Error: 'npx' not found. Please install Node.js/npm.")
        return

    # Start localtunnel on port 80 (Nginx port)
    # Use -y to skip prompt
    process = subprocess.Popen(
        ["npx", "-y", "localtunnel", "--port", "80"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    url = None
    print("Waiting for LocalTunnel to assign a URL...\n")
    
    # Read output until we find the URL
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        match = re.search(r'your url is: (https://[a-zA-Z0-9-.]+\.loca\.lt)', line)
        if match:
            url = match.group(1)
            print(f"\n\n[+] Found LocalTunnel URL: {url}\n")
            break
            
    if url:
        print("\n" + "="*60)
        print(f"🚀 PIPELINE IS READY (via LocalTunnel)!")
        print(f"👉 Access your dashboard at: {url}")
        print("="*60 + "\n")
        print("(Press Ctrl+C to stop the tunnel)\n")
        
        # Keep printing logs
        try:
            for line in iter(process.stdout.readline, ''):
                print(line, end='')
        except KeyboardInterrupt:
            print("\nStopping tunnel...")
            process.terminate()
            sys.exit(0)
    else:
        print(" ❌ Failed to get LocalTunnel URL.")
        process.terminate()

if __name__ == "__main__":
    main()
