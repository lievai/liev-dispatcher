import json
import os
import socketio
import logging
from config.config import Config
from liev_llm_manager.manager import get_manager

class DispatcherControllerSocketio:
    def __init__(self):
        self.__config = Config('dispatcher')

        # Configure logging
        logging.basicConfig(
            level=self.__config.get('LOG_LEVEL', 'DEBUG'),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.__logger = logging.getLogger(__name__)

        self._connection_map = {}
        

    def __get_client(self, socketio_server):
        client = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=1,
            reconnection_delay_max=5,
            request_timeout=60
        )

        @client.event
        def reply(data):
            socketio_server.emit('reply', data, to=self._connection_map[client.get_sid()])
            self.__logger.debug(f"Emit data event to {self._connection_map[client.get_sid()]}\n{data}")

        @client.event
        def finish(data):
            socketio_server.emit('finish', data, to=self._connection_map[client.get_sid()])
            del(self._connection_map[client.get_sid()])
            client.disconnect()

        return client
    
    def initialize_stream(self, request_data, socketio_server, request_sid):
        client = self.__get_client(socketio_server)
        manager = get_manager()
        all_llms = manager.get_all_llms()
        

        try:
            llm_name = ''
            if 'llm_name' in request_data:
                llm_name = request_data.get('llm_name')
                self.__logger.debug(f'Socket.io calling by llm_name parameter: {llm_name}')
            elif 'function' in request_data:
                llm_name = manager.get_llm_by_priority(type = request_data['function'], priority = 1)['name']
                self.__logger.debug(f'Socket.io calling by function parameter: {llm_name}')
            elif 'type' in request_data:
                llm_name = manager.get_llm_by_priority(type = request_data['type'], priority = 1)['name']
                self.__logger.debug(f'Socket.io calling by type parameter: {llm_name}')
            else:
                self.__logger.error('You must specify an llm_name or function/type')
                client.emit('error','You must specify an llm_name or function/type')

            for llm in all_llms:
                if llm_name == llm['name']:
                    if 'stream_url' in llm and len(llm['stream_url']) > 0:
                        try:
                            client.connect(llm['stream_url'],
                                        transports=['websocket'], 
                                        auth=(llm['username'], llm['password']))
                            self.__logger.debug(f"Socket.io dispatcher successfully connected to {llm_name} at {llm['stream_url']}")
                            break
                        except Exception as e:
                            self.__logger.error(f"Failed to connect to {llm_name} at {llm['stream_url']}: {e}")
                    else:
                        socketio_server.emit('error', f"{llm_name} doesn't support Socket.io streaming")
                else:
                    continue

            self._connection_map[client.get_sid()] = request_sid
            client_username = request_data['Liev-Client-Username'] if request_data['Liev-Client-Username'] else 'unknown'
            self.__logger.info(f'LLM Request: socket.io response LLM_Name: {llm["name"]}, User: {client_username},')
            client.emit('response', json.dumps(request_data))

        except Exception as e:
            socketio_server.emit('error,'f'Error calling socket.io llm: {e}')
            self.__logger.error(f'Error calling socket.io llm: {e}', exc_info=True)