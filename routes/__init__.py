# routes/__init__.py
from flask import Blueprint
from .auth_routes import auth_bp
from .dashboard_routes import dashboard_bp

__all__ = ['auth_bp', 'dashboard_bp']