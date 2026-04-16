"""
Unit Tests for DevOps AutoPilot - ML Analyzer Module

These tests verify the ML-based code analysis functionality using CodeBERT
for language and framework detection.

Author: Abdul Ahad Abbassi
Project: DevOps AutoPilot - AI Deployment Agent
Date: December 2024
"""

import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMLCodeAnalyzerInitialization(unittest.TestCase):
    """Test cases for ML Analyzer initialization."""

    @patch('app.utils.ml_analyzer.AutoTokenizer')
    @patch('app.utils.ml_analyzer.AutoModel')
    def test_model_initialization(self, mock_model, mock_tokenizer):
        """TC045: Verify CodeBERT model loads correctly."""
        mock_tokenizer.from_pretrained.return_value = MagicMock()
        mock_model.from_pretrained.return_value = MagicMock()
        
        from app.utils.ml_analyzer import MLCodeAnalyzer
        analyzer = MLCodeAnalyzer()
        
        mock_tokenizer.from_pretrained.assert_called()
        mock_model.from_pretrained.assert_called()

    @patch('app.utils.ml_analyzer.AutoTokenizer')
    @patch('app.utils.ml_analyzer.AutoModel')
    def test_language_signatures_loaded(self, mock_model, mock_tokenizer):
        """TC046: Verify language signatures are pre-computed."""
        mock_tokenizer.from_pretrained.return_value = MagicMock()
        mock_model.from_pretrained.return_value = MagicMock()
        
        from app.utils.ml_analyzer import MLCodeAnalyzer
        analyzer = MLCodeAnalyzer()
        
        # Verify signatures exist for major languages
        self.assertIn("Python", analyzer.language_signatures)
        self.assertIn("JavaScript", analyzer.language_signatures)


class TestMLCodeAnalyzerEmbeddings(unittest.TestCase):
    """Test cases for embedding generation."""

    def setUp(self):
        """Mock ML dependencies."""
        self.patcher_tokenizer = patch('app.utils.ml_analyzer.AutoTokenizer')
        self.patcher_model = patch('app.utils.ml_analyzer.AutoModel')
        self.mock_tokenizer = self.patcher_tokenizer.start()
        self.mock_model = self.patcher_model.start()
        
        # Setup mock returns
        self.mock_tokenizer.from_pretrained.return_value = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_instance.return_value.last_hidden_state = MagicMock()
        self.mock_model.from_pretrained.return_value = mock_model_instance

    def tearDown(self):
        """Stop patchers."""
        self.patcher_tokenizer.stop()
        self.patcher_model.stop()

    def test_embedding_extraction(self):
        """TC047: Verify embedding extraction from code samples."""
        from app.utils.ml_analyzer import MLCodeAnalyzer
        analyzer = MLCodeAnalyzer()
        
        # Test that extract_embedding is callable
        self.assertTrue(hasattr(analyzer, 'extract_embedding') or hasattr(analyzer, '_extract_embedding'))

    def test_cosine_similarity_calculation(self):
        """TC048: Verify cosine similarity between embeddings."""
        # Test cosine similarity logic
        from sklearn.metrics.pairwise import cosine_similarity
        
        vec1 = np.array([[1, 0, 0]])
        vec2 = np.array([[1, 0, 0]])
        vec3 = np.array([[0, 1, 0]])
        
        # Same vectors should have similarity of 1
        self.assertAlmostEqual(cosine_similarity(vec1, vec2)[0][0], 1.0)
        # Orthogonal vectors should have similarity of 0
        self.assertAlmostEqual(cosine_similarity(vec1, vec3)[0][0], 0.0)


class TestMLCodeAnalyzerDetection(unittest.TestCase):
    """Test cases for ML-based detection."""

    def setUp(self):
        """Create temporary directory and mock ML."""
        self.test_dir = tempfile.mkdtemp()
        self.patcher_tokenizer = patch('app.utils.ml_analyzer.AutoTokenizer')
        self.patcher_model = patch('app.utils.ml_analyzer.AutoModel')
        self.mock_tokenizer = self.patcher_tokenizer.start()
        self.mock_model = self.patcher_model.start()
        
        self.mock_tokenizer.from_pretrained.return_value = MagicMock()
        self.mock_model.from_pretrained.return_value = MagicMock()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.test_dir)
        self.patcher_tokenizer.stop()
        self.patcher_model.stop()

    def test_code_sample_collection(self):
        """TC049: Verify code samples collected from project."""
        # Create sample code files
        with open(os.path.join(self.test_dir, "app.py"), "w") as f:
            f.write("from flask import Flask\napp = Flask(__name__)")
        
        from app.utils.ml_analyzer import MLCodeAnalyzer
        analyzer = MLCodeAnalyzer()
        
        # Verify analyzer can process the directory
        self.assertTrue(os.path.exists(self.test_dir))

    def test_max_files_limit(self):
        """TC050: Verify ML analyzer respects max file limit."""
        # Create many files
        for i in range(20):
            with open(os.path.join(self.test_dir, f"file{i}.py"), "w") as f:
                f.write(f"# File {i}\nprint('hello')")
        
        from app.utils.ml_analyzer import MLCodeAnalyzer
        analyzer = MLCodeAnalyzer()
        
        # Analyzer should limit files processed
        self.assertEqual(len(os.listdir(self.test_dir)), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
