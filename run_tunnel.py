import subprocess
import re
import time
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
            url = match.group(1)
            print(f"\n\n[+] Found new Tunnel URL: {url}\n")
            break
            
    if url:
        print("Updating configuration files with new URL...")
        
        # Update docker-compose.yml
        try:
            with open('docker-compose.yml', 'r') as f:
                dc = f.read()
            dc = re.sub(r'NEXT_PUBLIC_API_URL:\s+https?://[a-zA-Z0-9-.]+(trycloudflare\.com|localhost:\d+)', f'NEXT_PUBLIC_API_URL: {url}', dc)
            dc = re.sub(r'NEXT_PUBLIC_WS_URL:\s+wss?://[a-zA-Z0-9-.]+(trycloudflare\.com|localhost:\d+)', f'NEXT_PUBLIC_WS_URL: {url.replace("https://", "wss://")}', dc)
            with open('docker-compose.yml', 'w') as f:
                f.write(dc)
            print(" ✅ Updated docker-compose.yml")
        except Exception as e:
            print(f" ❌ Error updating docker-compose.yml: {e}")
            
        # Update root .env and backend/.env
        for env_path in ['.env', 'backend/.env']:
            try:
                with open(env_path, 'r') as f:
                    env_data = f.read()
                # Replace the cloudflare origin in the array if it exists
                env_data = re.sub(r'"https://[a-zA-Z0-9-]+\.trycloudflare\.com"', f'"{url}"', env_data)
                with open(env_path, 'w') as f:
                    f.write(env_data)
                print(f" ✅ Updated {env_path}")
            except Exception as e:
                print(f" ❌ Error updating {env_path}: {e}")
            
        print("\nRestarting Docker containers with new config...")
        # Next.js NEXT_PUBLIC_ env vars are baked at BUILD time, not runtime.
        # We must rebuild the frontend image for the new tunnel URL to work.
        subprocess.run(["docker", "compose", "up", "-d", "--build", "frontend"])
        
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
