from src.utils.DiscoveryUtils import DiscoveryUtils
from functools import wraps
from flask import  Response, request
import json

async def get_service_response(endpoint):
    return await DiscoveryUtils.get_instance().get_client().do_service("authentication-service", endpoint)

def decorator(f):
    @wraps(f)
    async def decorator_function(*args, **kwargs):
        user_name = request.headers.get('X-USERNAME')
        endpoint = f"/internal/auth/v1/account/{user_name}"

        try:
            await get_service_response(endpoint)
        except Exception as e:
            return Response(response=json.dumps({"error": "Usuário não tem permissão."}), status=403, content_type='application/json')

        return f(*args, **kwargs)
    return decorator_function
