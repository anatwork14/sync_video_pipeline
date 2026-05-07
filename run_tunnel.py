import subprocess
import re
import sys

def main():
    print("Starting Cloudflare tunnel...")
    # Start cloudflared in the background
    process = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:80"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    url = None
    print("Waiting for Cloudflare to assign a URL...\n")
    # Read output until we find the URL
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        match = re.search(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)', line)
        if match:
            candidate = match.group(1)
            if "api.trycloudflare.com" in candidate:
                continue
            url = candidate
            print(f"\n\n[+] Found new Tunnel URL: {url}\n")
            break
            
    if url:
        print("\n" + "="*60)
        print(f"🚀 PIPELINE IS READY!")
        print(f"👉 Access your dashboard at: {url}")
        print("="*60 + "\n")
        print("(Press Ctrl+C to stop the tunnel)\n")
        
        # Keep printing tunnel logs
        try:
            for line in iter(process.stdout.readline, ''):
                print(line, end='')
        except KeyboardInterrupt:
            print("\nStopping tunnel...")
            process.terminate()
            sys.exit(0)

if __name__ == "__main__":
    main()
