import socket
import json

def get_docker_logs():
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect("/var/run/docker.sock")
        # Find container ID for backend
        request = b"GET /containers/json?filters={\"name\":[\"backend\"]} HTTP/1.0\r\n\r\n"
        client.sendall(request)
        response = b""
        while True:
            data = client.recv(4096)
            if not data:
                break
            response += data
            
        parts = response.split(b"\r\n\r\n", 1)
        if len(parts) == 2:
            containers = json.loads(parts[1].decode())
            if containers:
                cid = containers[0]["Id"]
                
                # Get logs
                client2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client2.connect("/var/run/docker.sock")
                req2 = f"GET /containers/{cid}/logs?stdout=1&stderr=1&tail=50 HTTP/1.0\r\n\r\n".encode()
                client2.sendall(req2)
                res2 = b""
                while True:
                    data = client2.recv(4096)
                    if not data:
                        break
                    res2 += data
                
                print("LOGS:\n", res2.split(b"\r\n\r\n", 1)[-1].decode(errors='replace'))
    except Exception as e:
        print("Error:", e)

get_docker_logs()
