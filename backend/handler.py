"""Lambda entry point. Uvicorn is still what runs this locally and in Docker."""

from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="off")
