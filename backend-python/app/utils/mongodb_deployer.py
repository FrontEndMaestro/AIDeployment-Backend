def deploy_mongodb_if_needed(namespace: str = "default") -> Dict:
    """Deploy MongoDB in Kubernetes if not already running"""
    
    try:
        # Check if MongoDB already exists
        check = subprocess.Popen(
            ["kubectl", "get", "deployment", "mongodb", "-n", namespace],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout_bytes, _ = check.communicate(timeout=10)
        
        if check.returncode == 0:
            print("✅ MongoDB already running")
            return {"success": True, "already_exists": True}
        
        # Deploy MongoDB
        print("🗄️ Deploying MongoDB...")
        
        mongodb_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mongodb
  labels:
    app: mongodb
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mongodb
  template:
    metadata:
      labels:
        app: mongodb
    spec:
      containers:
      - name: mongodb
        image: mongo:7.0
        ports:
        - containerPort: 27017
        env:
        - name: MONGO_INITDB_DATABASE
          value: "notes_app"
---
apiVersion: v1
kind: Service
metadata:
  name: mongodb
  labels:
    app: mongodb
spec:
  type: ClusterIP
  selector:
    app: mongodb
  ports:
  - port: 27017
    targetPort: 27017
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(mongodb_manifest)
            temp_file = f.name
        
        process = subprocess.Popen(
            ["kubectl", "apply", "-f", temp_file, "--validate=false"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout_bytes, stderr_bytes = process.communicate(timeout=30)
        
        os.unlink(temp_file)
        
        if process.returncode == 0:
            print("✅ MongoDB deployed")
            return {"success": True, "mongodb_url": "mongodb://mongodb:27017/notes_app"}
        else:
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            return {"success": False, "message": stderr}
    
    except Exception as e:
        return {"success": False, "message": str(e)}