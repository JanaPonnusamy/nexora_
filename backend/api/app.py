from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.database import get_connection

from controllers.auth_controller import router as auth_router
from controllers.tenant_controller import router as tenant_router
from controllers.store_controller import router as store_router
from controllers.role_controller import router as role_router
from controllers.user_role_controller import router as user_role_router
from controllers.module_controller import router as module_router
from controllers.role_module_access_controller import router as role_module_access_router
from controllers.user_controller import router as user_router, relations_router as user_relations_router
from controllers.permission_controller import router as permission_router
from modules.sync.router import router as sync_router

app = FastAPI(title='NEXORA API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(tenant_router)
app.include_router(store_router)
app.include_router(role_router)
app.include_router(user_role_router)
app.include_router(module_router)
app.include_router(role_module_access_router)
app.include_router(user_router)
app.include_router(user_relations_router)
app.include_router(permission_router)
app.include_router(sync_router)

@app.get('/health')
def health():
    return {'status':'healthy'}

@app.get('/health/db')
def health_db():
    try:
        conn = get_connection()
        conn.close()
        return {'status':'healthy','database':'connected'}
    except Exception as ex:
        return {'status':'failed','error':str(ex)}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
