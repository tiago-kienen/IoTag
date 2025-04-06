import json
from flask import Flask, Response, request
#from security.Decorator import decorator
from services.FieldIdentifierService import FieldIdentifierService
from utils.DiscoveryUtils import DiscoveryUtils


app = Flask(__name__)
DiscoveryUtils.get_instance()

@app.route('/field-identifier-service/opa')
# @decorator
def health_check():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        type = int(request.args.get('type'))

        result = FieldIdentifierService().identify_fields(lat, lon, type)
        return Response(response=json.dumps(result), status=200, mimetype='application/json')
    except (TypeError, ValueError) as e:
        return Response(response=json.dumps({"error": "Invalid input parameters"}), status=400, mimetype='application/json')

if __name__ == '__main__':
    app.run(port=5000, debug=False)



# from fastapi import FastAPI
#
# app = FastAPI()
#
#
# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
