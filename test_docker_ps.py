import urllib.request
import json
try:
    req = urllib.request.Request("http://localhost/containers/json", headers={"Host": "localhost"})
    # Oh wait, we need to use a Unix socket!
except Exception:
    pass
