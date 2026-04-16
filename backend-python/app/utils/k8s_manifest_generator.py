import yaml
from typing import Dict, List


def generate_k8s_manifests(
    deployment_name: str,
    image: str,
    port: int = 8000,
    node_port: int = 30001,
    env_variables: List[str] = None,
    mongodb_url: str = "mongodb://host.docker.internal:27017",
    labels: Dict[str, str] = None,
    replicas: int = 1,
    namespace: str = "default"
) -> Dict[str, str]:
    """Generate Kubernetes manifests"""
    
    if labels is None:
        labels = {}
    if env_variables is None:
        env_variables = []
    
    clean_labels = {}
    for key, value in labels.items():
        clean_key = str(key).replace("_", "-").lower()
        clean_value = str(value).replace("_", "-").replace(" ", "-").lower()[:63].strip("-")
        clean_labels[clean_key] = clean_value
    
    base_labels = {
        "app": deployment_name,
        "managed-by": "devops-autopilot",
        **clean_labels
    }
    
    configmap_yaml = generate_configmap(
        name=deployment_name,
        namespace=namespace,
        labels=base_labels,
        mongodb_url=mongodb_url,
        env_variables=env_variables,
        port=port
    )
    
    deployment_yaml = generate_deployment(
        name=deployment_name,
        namespace=namespace,
        image=image,
        port=port,
        replicas=replicas,
        labels=base_labels,
        configmap_name=deployment_name
    )
    
    service_yaml = generate_service(
        name=deployment_name,
        namespace=namespace,
        port=port,
        node_port=node_port,
        labels=base_labels
    )
    
    return {
        "deployment": deployment_yaml,
        "service": service_yaml,
        "configmap": configmap_yaml,
        "deployment_name": deployment_name,
        "service_port": node_port
    }


def generate_configmap(
    name: str,
    namespace: str,
    labels: Dict[str, str],
    mongodb_url: str,
    env_variables: List[str],
    port: int
) -> str:
    """Generate ConfigMap - CRITICAL: All values MUST be strings"""
    
    # Extract DB name
    db_name = "app_db"
    if '/' in mongodb_url and mongodb_url.split('/')[-1]:
        db_name = mongodb_url.split('/')[-1]
    
    # CRITICAL: Convert ALL values to strings explicitly
    config_data = {}
    
    # MongoDB URLs - all variations
    mongo_vars = {
        "MONGODB_URI": mongodb_url,
        "MONGO_URI": mongodb_url,
        "MONGO_URL": mongodb_url,
        "DB_URL": mongodb_url,
        "DATABASE_URL": mongodb_url,
        "MONGODB_URL": mongodb_url
    }
    
    for key, value in mongo_vars.items():
        config_data[key] = str(value)
    
    # Other required vars
    other_vars = {
        "DB_NAME": db_name,
        "DATABASE_NAME": db_name,
        "NODE_ENV": "production",
        "ENVIRONMENT": "production",
        "HOST": "0.0.0.0",
        "PORT": str(port),
        "JWT_SECRET": "your-secret-key",
        "SECRET_KEY": "your-secret-key",
        "CORS_ORIGIN": "*"
    }
    
    for key, value in other_vars.items():
        config_data[key] = str(value)
    
    # Add custom env variables
    for env_var in env_variables:
        if env_var and isinstance(env_var, str):
            if '=' in env_var:
                k, v = env_var.split('=', 1)
                config_data[k.strip()] = str(v.strip())
            else:
                config_data[env_var.strip()] = ""
    
    # Build ConfigMap structure
    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": str(name),
            "namespace": str(namespace),
            "labels": labels
        },
        "data": config_data
    }
    
    # Dump to YAML with explicit string handling
    yaml_output = yaml.dump(
        configmap,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        default_style=None
    )
    
    return yaml_output


def generate_deployment(
    name: str,
    namespace: str,
    image: str,
    port: int,
    replicas: int,
    labels: Dict[str, str],
    configmap_name: str
) -> str:
    """Generate Deployment YAML"""
    
    deployment_dict = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": str(name),
            "namespace": str(namespace),
            "labels": labels
        },
        "spec": {
            "replicas": int(replicas),
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {
                    "maxSurge": 1,
                    "maxUnavailable": 0
                }
            },
            "selector": {
                "matchLabels": {
                    "app": str(name)
                }
            },
            "template": {
                "metadata": {
                    "labels": labels
                },
                "spec": {
                    "containers": [{
                        "name": str(name),
                        "image": str(image),
                        "imagePullPolicy": "Always",
                        "ports": [{
                            "name": "http",
                            "containerPort": int(port),
                            "protocol": "TCP"
                        }],
                        "envFrom": [{
                            "configMapRef": {
                                "name": str(configmap_name)
                            }
                        }],
                        "resources": {
                            "requests": {
                                "memory": "256Mi",
                                "cpu": "250m"
                            },
                            "limits": {
                                "memory": "512Mi",
                                "cpu": "500m"
                            }
                        }
                    }],
                    "restartPolicy": "Always"
                }
            }
        }
    }
    
    return yaml.dump(deployment_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)


def generate_service(
    name: str,
    namespace: str,
    port: int,
    node_port: int,
    labels: Dict[str, str]
) -> str:
    """Generate Service YAML"""
    
    service_dict = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": str(name),
            "namespace": str(namespace),
            "labels": labels
        },
        "spec": {
            "type": "NodePort",
            "selector": {
                "app": str(name)
            },
            "ports": [{
                "name": "http",
                "protocol": "TCP",
                "port": int(port),
                "targetPort": int(port),
                "nodePort": int(node_port)
            }]
        }
    }
    
    return yaml.dump(service_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)