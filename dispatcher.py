import functools
import os
import logging
from flask_restful import Api
from flask import Flask, Response, request
import json
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from config.config import Config
from controllers.dispatcher_controller import DispatcherController
from controllers.dispatcher_controller_socketio import DispatcherControllerSocketio
from exception.exceptions import FimNotSupportedException
from liev_llm_manager.etcd import EtcdEndpointManager
from liev_llm_manager.exception.exception import LLMMissingRequiredFieldException
from auth.auth import AuthHelper
from utils import print_banner
from flask_socketio import SocketIO, disconnect, emit
from flask_cors import CORS

from liev_llm_manager.manager import get_manager

# Constants
json_payload_msg = 'JSON load conversion problem. Not a dict ! Are you using data payload  ?'
json_load_prob_msg = 'JSON load problem!'

#Init
print_banner()

#Configuration Load
load_dotenv()
config = Config('dispatcher')

## Logging in containers MUST be console.
logging.basicConfig(level=config.get('LOG_LEVEL', 'DEBUG'), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get a LLM manager dynamically
manager = get_manager()

# Get the dispatcher controller
controller = DispatcherController()

app = Flask(__name__)
# Set the secret key. Random generated
app.secret_key = '2$sg^zL+uerix"3'

api = Api(app)

#Auth
auth_mode = config.get('AUTH_MODE', 'basic')
auth = AuthHelper(auth_mode).get_flask_auth()
llm_admin_role = config.get('AUTH_LLM_ADMIN_ROLE_NAME', 'LLM.Admin')
llm_user_role = config.get('AUTH_LLM_USER_ROLE_NAME', 'LLM.User')


#----------------------------------------------------------------------------------------------------
# Admin Endpoints
#----------------------------------------------------------------------------------------------------

# POST AN LLM
@app.route('/v1/llm', methods=['POST'])
@auth.login_required(role=llm_admin_role)
def post_endpoint():
    try:
        data = request.get_json()
        manager.create_llm(
                            name = data['name'],
                            model = data['model'],
                            url = data['url'],
                            username = data['username'],
                            password = data['password'],
                            response_mime = data['response_mime'],
                            is_external = data['is_external'],
                            system_message = data['system_message'] if 'system_message' in data else '',
                            prompt_mask = data['prompt_mask'] if 'prompt_mask' in data else '',
                            stream_url = data['stream_url'] if 'stream_url' in data else '',
                            http_stream_url = data['http_stream_url'] if 'http_stream_url' in data else '', 
                            fim_url = data['fim_url'] if 'fim_url' in data else '',                       
        )
        logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        return 'Success',201
    except LLMMissingRequiredFieldException as llmex:
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}', exc_info=True)
        return llmex.message, 400
    except Exception as e:
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}', exc_info=True)
        logger.error(f"Error calling post_endpoint: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500

# POST AN LLM
@app.route('/v1/llm', methods=['PATCH'])
@auth.login_required(role=llm_admin_role)
def update_endpoint():
    try:
        data = request.get_json()
        manager.update_llm(
                            name = data['name'],
                            model = data['model'],
                            url = data['url'],
                            username = data['username'],
                            password = data['password'],
                            response_mime = data['response_mime'],
                            is_external = data['is_external'],
                            system_message = data['system_message'] if 'system_message' in data else '',
                            prompt_mask = data['prompt_mask'] if 'prompt_mask' in data else '',
                            stream_url = data['stream_url'] if 'stream_url' in data else '',
                            http_stream_url = data['http_stream_url'] if 'http_stream_url' in data else '',  
                            fim_url = data['fim_url'] if 'fim_url' in data else '',                        
        )
        logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        return 'Success',201
    except LLMMissingRequiredFieldException as llmex:
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}', exc_info=True)
        return llmex.message, 400
    except Exception as e:
        logger.error(f"Error calling post_endpoint: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500


# PUT A TYPE AND PRIORITY FOR AN LLM
@app.route('/v1/llm_type', methods=['POST','PUT'])
@auth.login_required(role=llm_admin_role)
def post_type():
    try:
        data = request.get_json()
        manager.create_llm_type(
                            data['name'],
                            data['type'],
                            data['priority'],                   
        )
        logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        return 'Success',201
    except LLMMissingRequiredFieldException as llmex:
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        return llmex.message, 400
    except Exception as e:
        logger.error(f"Error calling post_endpoint: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500

# DELETE A TYPE AND PRIORITY FOR AN LLM
@app.route('/v1/llm_type/<type_str>/<llm_name>', methods=['DELETE'])
@auth.login_required(role=llm_admin_role)
def delete_type(type_str, llm_name):
    try:
        manager.delete_llm_type(
                            llm_name,
                            type_str,
        )
        logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        return 'Success',202
    except Exception as e:
        logger.error(f"Error calling delete_llm_type: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500


# GET ALL LLMS
@app.route('/v1/llm', methods=['GET'])
@auth.login_required(role=llm_user_role)
def get_llms():
    # Remove the sensible fields
    filtered_fields_llms = []
    for llm in manager.get_all_llms():
        filtered_field_llm = {key: value for key, value in llm.items() if key not in ['username', 'password']}
        filtered_fields_llms.append(filtered_field_llm)
    logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
    return json.dumps(filtered_fields_llms), 200

# DELETE AN LLM
@app.route('/v1/llm/<llm_name>', methods=['DELETE'])
@auth.login_required(role=llm_admin_role)
def delete_llm(llm_name):
    try:
        manager.delete_llm(llm_name)
        logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        return 'Success',204
    except Exception as e:
        logger.error(f"Error calling delete_llm: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500



# GET ALL LLMS AND TYPES
@app.route('/v1/llms_and_types', methods=['GET'])
@auth.login_required(role=llm_user_role)
def get_llms_types():
    llms = manager.get_all_llms_and_types()
    llms = []
    # Filter only Socket.io capable LLMs
    if request.args.get('socketio') == 'true':
        for llm in manager.get_all_llms_and_types():
            if 'stream_url' in llm and len(llm['stream_url']) > 0:
                llms.append(llm)
    # Filter only HTTP Stream capable LLMs
    elif request.args.get('stream') == 'true':
        for llm in manager.get_all_llms_and_types():
            if 'http_stream_url' in llm and len(llm['http_stream_url']) > 0:
                llms.append(llm)
    else:
        llms = manager.get_all_llms_and_types()
    # Remove the sensible fields
    filtered_fields_llms = []
    for llm in llms:
        filtered_field_llm = {key: value for key, value in llm.items() if key not in ['url', 'fim_url', 'stream_url','http_stream_url', 'api', 'username', 'password', 'prompt_mask', 'system_message']}
        filtered_fields_llms.append(filtered_field_llm)
    logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
    return json.dumps(filtered_fields_llms), 200

# GET LLMS BY TYPE
@app.route('/v1/llms_and_types/<type_str>', methods=['GET'])
@auth.login_required(role=llm_user_role)
def get_llms_types_per_type(type_str):
    llms = []
    # Filter only Socket.io capable LLMs
    if request.args.get('socketio') == 'true':
        for llm in manager.get_llms_by_type(type_str):
            if 'stream_url' in llm and len(llm['stream_url']) > 0:
                llms.append(llm)
    # Filter only HTTP Stream capable LLMs
    elif request.args.get('stream') == 'true':
        for llm in manager.get_all_llms_and_types():
            if 'http_stream_url' in llm and len(llm['http_stream_url']) > 0:
                llms.append(llm)
    else:
        llms = manager.get_llms_by_type(type_str)
    # Remove the sensible fields
    filtered_fields_llms = []
    for llm in llms:
        filtered_field_llm = {key: value for key, value in llm.items() if key not in ['url', 'fim_url', 'stream_url','http_stream_url', 'api', 'username', 'password', 'prompt_mask', 'system_message']}
        filtered_fields_llms.append(filtered_field_llm)
    logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
    return json.dumps(filtered_fields_llms), 200

@app.route('/v1/llms/<name>/<type>', methods=['GET'])
@auth.login_required(role=llm_user_role)
def get_llm(name, type):
    logger.info(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
    return manager

#----------------------------------------------------------------------------------------------------
# HTTP Response Endpoints
#----------------------------------------------------------------------------------------------------

@app.route('/response', methods=['GET','POST'])
@auth.login_required(role=llm_user_role)
def response():
    data = request.data
    try:
        data = json.loads(data)
    except Exception as e :
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        logger.error(f"{json_load_prob_msg}: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500

    if isinstance(data, dict) == False:
        return json.dumps(json_payload_msg), 500
    
    return controller.get_response(data, auth)


@app.route('/fim', methods=['GET','POST'])
@auth.login_required(role=llm_user_role)
def fim():
    data = request.data
    try:
        data = json.loads(data)
    except Exception as e :
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        logger.error(f"{json_load_prob_msg}: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500

    if isinstance(data, dict) == False:
        return json.dumps(json_payload_msg), 500
    try:
        return controller.get_response(data, auth, True)
    except FimNotSupportedException as fn:
        logger.error(e, exc_info=True)
        return json.dumps(fn.message), 500
    
#----------------------------------------------------------------------------------------------------
# HTTP Streaming Response Endpoints
#----------------------------------------------------------------------------------------------------

@app.route('/stream', methods=['GET','POST'])
@auth.login_required(role=llm_user_role)
def stream():
    data = request.data
    try:
        data = json.loads(data)
    except Exception as e :
        logger.error(f'Request: {request.method} {request.path}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
        logger.error(f"{json_load_prob_msg}: {e}", exc_info=True)
        return json.dumps("JSON load problem !"), 500

    if isinstance(data, dict) == False:
        return json.dumps(json_payload_msg), 500
    return controller.get_response(data, auth, stream = True)


#----------------------------------------------------------------------------------------------------
# Socket.io Response Endpoints
#----------------------------------------------------------------------------------------------------

CORS(app)  # Habilitar CORS
socketio_app = SocketIO(app, cors_allowed_origins="*", ping_timeout=120, ping_interval=25)

controller_stream = DispatcherControllerSocketio()

def authenticated_only(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not authenticated_user:
            emit('error', 'Invalid auth')
            disconnect()
        else:
            return f(*args, **kwargs)
    return wrapped

@socketio_app.on('connect')
def connect_handler(auth):
    global authenticated_user
    auth_result = AuthHelper('basic').verify_password(auth[0], auth[1])
    if auth_result:
        authenticated_user = True
    else:
        authenticated_user = False
        emit('error', 'Invalid auth')
        disconnect()

@socketio_app.on('response')
@authenticated_only
def handle_response(jsondata):
    try:
        data = json.loads(jsondata)
    except Exception as e:
        logger.error(f"{json_load_prob_msg}: {e}")
        emit('error', "JSON load problem !")

    if not isinstance(data, dict):
        logger.error(f"{json_load_prob_msg}: Not a dictionary")
        emit('error', json_payload_msg)
    else:
        controller_stream.initialize_stream(data, socketio_app, request.sid)

#----------------------------------------------------------------------------------------------------
# HTTP Healthchecks - Do not remove
#----------------------------------------------------------------------------------------------------

@app.route('/healthz')
def liveness():
    return json.dumps({'status': 'OK'})

# Health check endpoint for readiness probe
@app.route('/readyz')
def readiness():
    return json.dumps({'status': 'OK'})
