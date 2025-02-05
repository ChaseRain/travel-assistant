from fastapi import FastAPI
from app.core.config import settings
from app.routers import customer_support

# 第六部分 - 主应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.include_router(
    customer_support.router,
    prefix=f"{settings.API_V1_STR}/customer-support",
    tags=["customer-support"]
)

@app.get("/")
def read_root():
    return {"message": "Welcome to Travel Assistant Support Bot API"}