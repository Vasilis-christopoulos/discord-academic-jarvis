# tests/conftest.py
import sys, os

# Insert the project root (one level up) onto sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
