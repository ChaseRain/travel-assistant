from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.routers import customer_router
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="客服支持系统 API",
    description="客服聊天和操作确认的 API 接口",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(
    customer_router.router,
    prefix="/api/v1",
    tags=["customer-support"]
)

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# 注册路由时添加错误处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    # 根据异常类型返回不同的状态码和信息
    if isinstance(exc, HTTPException):
        logger.error(f"HTTP error occurred: {exc.detail}")
        return {"detail": exc.detail, "status_code": exc.status_code}
    
    # 对于其他未知异常，返回 500 状态码
    logger.error(f"Unexpected error occurred: {exc}", exc_info=True)
    return {"detail": "Internal server error", "status_code": 500}

# 添加请求日志中间件
@app.middleware("http")
async def log_requests(request, call_next):
    import time
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"Request path: {request.url.path} - Time taken: {process_time:.2f}s")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
