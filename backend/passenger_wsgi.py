import os
import sys

# Add the project directory to the sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Import FastAPI application
from app.main import app as fastapi_app

# Convert FastAPI (ASGI) to standard WSGI to be compatible with cPanel Passenger
from a2wsgi import ASGIMiddleware
application = ASGIMiddleware(fastapi_app)
