from fastapi import FastAPI

from app.config import settings
from app.database import Base, engine
from app.routes.accounts import router as accounts_router
from app.routes.auth import router as auth_router

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.app_name}


app.include_router(auth_router)
app.include_router(accounts_router)


Base.metadata.create_all(bind=engine)
