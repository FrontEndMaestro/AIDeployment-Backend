import os
import json
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import numpy as np


def _safe_print(msg: str):
    """Print safely on Windows without emoji encoding crashes."""
    try:
        print(msg)
        sys.stdout.flush()
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))
        sys.stdout.flush()


try:
    import torch
    from transformers import AutoTokenizer, AutoModel
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_ML = True
except ImportError as e:
    _safe_print(f"[ML-WARN] ML libraries not available: {e}")
    HAS_ML = False


class MLCodeAnalyzer:
    """Pure ML-powered code analyzer using ONLY CodeBERT"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = "cpu"  # Force CPU for stability
        self.language_embeddings = {}
        self.framework_embeddings = {}
        self.ml_available = HAS_ML
        
        # Language signatures for embedding
        self.language_signatures = {
            "Python": "import def class self print return if elif else for while try except with as pass",
            "JavaScript": "const let var function => async await return if else for while try catch class extends",
            "TypeScript": "interface type const let var function => async await return class extends implements",
            "Java": "public class private static void String int import package extends implements",
            "Go": "package import func type struct interface return if else for range defer",
            "Ruby": "def class module require include attr_accessor attr_reader attr_writer end",
            "PHP": "<?php function class public private protected static namespace use return",
        }
        
        # Framework signatures for embedding
        self.framework_signatures = {
            "Flask": "from flask import Flask app.route render_template request jsonify Blueprint",
            "Django": "from django.conf import settings INSTALLED_APPS django.db.models django.urls path",
            "FastAPI": "from fastapi import FastAPI app.get app.post Depends HTTPException",
            "Express.js": "const express require('express') app.listen app.get app.post router",
            "Next.js": "import next getServerSideProps getStaticProps useEffect useState",
            "React": "import React useState useEffect useRef useContext createContext",
            "Vue.js": "import Vue createApp ref reactive computed watch",
            "Spring Boot": "@SpringBootApplication @RestController @GetMapping @PostMapping @Autowired",
            "Laravel": "use Illuminate namespace Route Model Controller Eloquent",
            "Rails": "ActiveRecord has_many belongs_to validates before_action",
        }
        
        if HAS_ML:
            self._initialize_model()
            if self.model:
                self._initialize_embeddings()
        else:
            _safe_print("[ML-WARN] ML libraries not installed. Please install: pip install torch transformers scikit-learn")
    
    def _initialize_model(self):
        """Initialize CodeBERT model"""
        try:
            _safe_print("[ML] Loading CodeBERT model (microsoft/codebert-base)...")
            model_name = "microsoft/codebert-base"
            
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            os.makedirs(cache_dir, exist_ok=True)
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir,
                trust_remote_code=True
            )
            self.model = AutoModel.from_pretrained(
                model_name,
                cache_dir=cache_dir,
                trust_remote_code=True
            )
            self.model.to(self.device)
            self.model.eval()
            
            _safe_print(f"[ML-OK] CodeBERT loaded successfully on {self.device}")
            self.ml_available = True
            
        except Exception as e:
            _safe_print(f"[ML-ERROR] CodeBERT loading failed: {e}")
            _safe_print("   Install required libraries: pip install torch transformers scikit-learn")
            self.model = None
            self.ml_available = False
    
    def _initialize_embeddings(self):
        """Pre-compute embeddings for all languages and frameworks"""
        if not self.model or not HAS_ML:
            _safe_print("[ML-WARN] Skipping embedding initialization (model not loaded)")
            return
        
        _safe_print("[ML] Computing language & framework embeddings...")
        
        try:
            for lang, signature in self.language_signatures.items():
                embedding = self._extract_embedding(signature)
                if embedding is not None:
                    self.language_embeddings[lang] = embedding
            
            for framework, signature in self.framework_signatures.items():
                embedding = self._extract_embedding(signature)
                if embedding is not None:
                    self.framework_embeddings[framework] = embedding
            
            _safe_print(f"[ML-OK] Computed {len(self.language_embeddings)} language embeddings")
            _safe_print(f"[ML-OK] Computed {len(self.framework_embeddings)} framework embeddings")
            
        except Exception as e:
            _safe_print(f"[ML-ERROR] Embedding initialization failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _extract_embedding(self, text: str) -> Optional[np.ndarray]:
        """Extract embedding from text using CodeBERT"""
        if not self.model or not HAS_ML or not text.strip():
            return None
        
        try:
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()
            
            return embedding
            
        except Exception as e:
            _safe_print(f"[ML-WARN] Embedding extraction failed: {e}")
            return None
    
    def analyze_project_structure(self, project_path: str) -> Dict:
        """Analyze project structure and collect code samples"""
        analysis = {
            "total_files": 0,
            "code_files": 0,
            "config_files": [],
            "key_files": [],
            "code_samples": []
        }
        
        important_files = [
            "package.json", "requirements.txt", "pom.xml",
            "composer.json", "go.mod", "Gemfile", "Cargo.toml"
        ]
        
        code_extensions = {".py", ".js", ".ts", ".java", ".go", ".rb", ".php"}
        
        try:
            for root, _, files in os.walk(project_path):
                if any(skip in root for skip in ["node_modules", "__pycache__", ".git", "venv", "dist", "build"]):
                    continue
                
                for file in files:
                    analysis["total_files"] += 1
                    file_path = os.path.join(root, file)
                    ext = Path(file).suffix.lower()
                    
                    if file in important_files:
                        analysis["key_files"].append(file)
                        analysis["config_files"].append(file_path)
                    
                    if ext in code_extensions:
                        analysis["code_files"] += 1
                        if len(analysis["code_samples"]) < 15:
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read(5000)
                                    if content.strip():
                                        analysis["code_samples"].append({
                                            "file": file,
                                            "ext": ext,
                                            "content": content
                                        })
                            except:
                                pass
        
        except Exception as e:
            _safe_print(f"[ML-WARN] Structure analysis error: {e}")
        
        return analysis
    
    def detect_language_ml(self, structure: Dict) -> Tuple[str, float]:
        """Detect language using ONLY CodeBERT embeddings"""
        
        if not self.model or not HAS_ML or not self.language_embeddings:
            return "Unknown", 0.0
        
        if not structure["code_samples"]:
            return "Unknown", 0.0
        
        try:
            code_texts = [sample["content"][:1000] for sample in structure["code_samples"][:10]]
            combined_code = "\n".join(code_texts)
            
            project_embedding = self._extract_embedding(combined_code)
            
            if project_embedding is None:
                return "Unknown", 0.0
            
            best_language = "Unknown"
            best_similarity = 0.0
            
            for lang, lang_embedding in self.language_embeddings.items():
                similarity = cosine_similarity(project_embedding, lang_embedding)[0][0]
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_language = lang
            
            confidence = float(best_similarity)
            _safe_print(f"   [ML] Language Detection: {best_language} (similarity: {confidence:.3f})")
            
            return best_language, confidence
            
        except Exception as e:
            _safe_print(f"   [ML-ERROR] Language detection failed: {e}")
            import traceback
            traceback.print_exc()
            return "Unknown", 0.0
    
    def detect_framework_ml(self, structure: Dict, language: str) -> Tuple[str, float]:
        """Detect framework using ONLY CodeBERT embeddings"""
        
        if not self.model or not HAS_ML or not self.framework_embeddings:
            return "Unknown", 0.0
        
        if not structure["code_samples"]:
            return "Unknown", 0.0
        
        try:
            code_texts = [sample["content"][:1000] for sample in structure["code_samples"][:10]]
            combined_code = "\n".join(code_texts)
            
            project_embedding = self._extract_embedding(combined_code)
            
            if project_embedding is None:
                return "Unknown", 0.0
            
            best_framework = "Unknown"
            best_similarity = 0.0
            
            for framework, fw_embedding in self.framework_embeddings.items():
                similarity = cosine_similarity(project_embedding, fw_embedding)[0][0]
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_framework = framework
            
            confidence = float(best_similarity)
            _safe_print(f"   [ML] Framework Detection: {best_framework} (similarity: {confidence:.3f})")
            
            return best_framework, confidence
            
        except Exception as e:
            _safe_print(f"   [ML-ERROR] Framework detection failed: {e}")
            import traceback
            traceback.print_exc()
            return "Unknown", 0.0
    
    def analyze_project(self, project_path: str) -> Dict:
        """Main ML analysis pipeline - PURE CodeBERT"""
        
        _safe_print("[ML] Starting PURE CodeBERT ML Analysis...")
        
        if not self.ml_available or not self.model:
            _safe_print("[ML-ERROR] CodeBERT not available! Cannot analyze.")
            return {
                "language": "Unknown",
                "language_confidence": 0.0,
                "framework": "Unknown",
                "framework_confidence": 0.0,
                "detection_method": "Failed - ML not available",
                "ml_available": False,
                "structure_analysis": {
                    "total_files": 0,
                    "code_files": 0,
                    "key_files": [],
                    "file_types": {}
                }
            }
        
        structure = self.analyze_project_structure(project_path)
        _safe_print(f"[ML] Found {structure['total_files']} files, {structure['code_files']} code files")
        
        if structure['code_files'] == 0:
            _safe_print("[ML-WARN] No code files found!")
            return {
                "language": "Unknown",
                "language_confidence": 0.0,
                "framework": "Unknown",
                "framework_confidence": 0.0,
                "detection_method": "Failed - No code files",
                "ml_available": self.ml_available,
                "structure_analysis": {
                    "total_files": structure["total_files"],
                    "code_files": 0,
                    "key_files": structure["key_files"],
                    "file_types": {}
                }
            }
        
        _safe_print("[ML] Detecting language...")
        language, lang_confidence = self.detect_language_ml(structure)
        
        _safe_print("[ML] Detecting framework...")
        framework, fw_confidence = self.detect_framework_ml(structure, language)
        
        _safe_print(f"[ML] Analysis Complete!")
        _safe_print(f"   Language: {language} (confidence: {lang_confidence:.2f})")
        _safe_print(f"   Framework: {framework} (confidence: {fw_confidence:.2f})")
        
        return {
            "language": language,
            "language_confidence": round(lang_confidence, 2),
            "framework": framework,
            "framework_confidence": round(fw_confidence, 2),
            "detection_method": "CodeBERT ML",
            "ml_available": self.ml_available,
            "structure_analysis": {
                "total_files": structure["total_files"],
                "code_files": structure["code_files"],
                "key_files": structure["key_files"],
                "file_types": {}
            }
        }


# Singleton instance
_ml_analyzer_instance = None

def get_ml_analyzer() -> MLCodeAnalyzer:
    """Get or create ML analyzer singleton"""
    global _ml_analyzer_instance
    if _ml_analyzer_instance is None:
        _ml_analyzer_instance = MLCodeAnalyzer()
    return _ml_analyzer_instance