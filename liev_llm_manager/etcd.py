import etcd3
import json
import logging
import os
from config.config import Config
from liev_llm_manager.exception.exception import LLMMissingRequiredFieldException
from liev_llm_manager.base_llm_manager import BaseLLMManager

name = 'EtcdEndpointManager'
class EtcdEndpointManager(BaseLLMManager):
    def __init__(self):
        super().__init__()
        self.__config = Config('dispatcher')
        self.__logger = logging.getLogger("EtcdEndpointManager")
        self.__etcd_host = self.__config.get('ETCD_HOST')
        self.__etcd_port = self.__config.get('ETCD_PORT')

        if None in (self.__etcd_host, self.__etcd_port):
            raise Exception("If using LLM_MANAGER_IMPL='etcd' you need to set ETCD_HOST and ETCD_PORT env vars!")

        try:
            self.__etcd = etcd3.client(host=self.__etcd_host, port=self.__etcd_port)
        except Exception as e:
            self.__logger.error(f"Error initializing EtcdEndpointManager: {e}", exc_info=True)

    def create_llm(self, 
                   name, 
                   model, 
                   url, 
                   username, 
                   password, 
                   response_mime,
                   system_message='', 
                   prompt_mask='', 
                   is_external = False,
                   stream_url = None,
                   http_stream_url = None,
                   fim_url = None):
        try:
            # Create item in etcd
            endpoint_data = {
                "name": name,
                "model": model,
                "url": url,
                "username": username,
                "password": password,
                "response_mime": response_mime,
                "system_message": system_message,
                "prompt_mask": prompt_mask,
                "is_external": is_external,
                "stream_url": stream_url if stream_url is not None else '',
                "http_stream_url": http_stream_url if http_stream_url is not None else '',
                "fim_url": fim_url if fim_url else None,
            }
            required_fields = ["name", "model", "url", "username", "password", "response_mime"]
            for field in required_fields:
                if field not in endpoint_data:
                    raise LLMMissingRequiredFieldException({"error": f"Missing required field: {field}"})

            self.__etcd.put(f"/llms/endpoints/{name}", json.dumps(endpoint_data))

        except Exception as e:
            self.__logger.error(f'Error creating LLM: {e}', exc_info=True)
    
    def create_llm_type(self, name, type, priority):
        try:
            # Fetch all items of the given type
            existing_items = self.get_llms_by_type(type)
            max_priority = max([item['priority'] for item in existing_items], default=0)
            
            # If priority is 0, set it to the highest available
            if priority == 0:
                priority = max_priority + 1

            # Ensure priority doesn't exceed the last available priority
            if priority > max_priority + 1:
                priority = max_priority + 1

            # Update priorities
            for item in existing_items:
                if item['priority'] >= priority:
                    item['priority'] += 1
                    self.__etcd.put(f"/llms/types/{type}/{item['name']}", json.dumps(item))

            # Create the new item with the desired priority
            type_data = {
                "type": type,
                "name": name,
                "priority": priority
            }
            self.__etcd.put(f"/llms/types/{type}/{name}", json.dumps(type_data))
        except Exception as e:
            self.__logger.error(f'Error creating LLM type: {e}', exc_info=True)


    def update_llm_type(self, name, type, priority):
        # In Etcd, create again will replace
        self.create_llm_type(name, type, priority)
    
    def delete_llm_type(self, name, type):
        try:
            # Delete the item from etcd
            self.__etcd.delete(f"/llms/types/{type}/{name}")
        except Exception as e:
            self.__logger.error(f"Error deleting LLM type: {e}", exc_info=True)
        
    def get_llm_by_name(self, name, type=None):
        try:
            if type is not None:
                type_value, type_metadata = self.__etcd.get(f"/llms/types/{type}/{name}")
                item_type = json.loads(type_value) if type_value else None

                endpoint_value, endpoint_metadata = self.__etcd.get(f"/llms/endpoints/{name}")
                item_endpoint = json.loads(endpoint_value) if endpoint_value else None

                if item_type and item_endpoint:
                    llm = {**item_type, **item_endpoint}
                    return llm
                return None
            else:
                endpoint_value, endpoint_metadata = self.__etcd.get(f"/llms/endpoints/{name}")
                item_endpoint = json.loads(endpoint_value) if endpoint_value else None

                return item_endpoint
        except Exception as e:
            self.__logger.error(f"Error getting LLM by name: {e}", exc_info=True)
            raise

    def get_all_llms(self):
        try:
            all_llms = []
            for value, metadata in self.__etcd.get_prefix("/llms/endpoints/"):
                item = json.loads(value)
                all_llms.append(item)
            return all_llms
        except Exception as e:
            self.__logger.error(f"Error getting all LLMs: {e}", exc_info=True)
            raise
            
    def get_all_llms_and_types(self):
        try:
            all_llms_list = []
            for type_value, type_metadata in self.__etcd.get_prefix("/llms/types/"):
                item_type = json.loads(type_value)
                endpoint_value, endpoint_metadata = self.__etcd.get(f"/llms/endpoints/{item_type['name']}")
                item_endpoint = json.loads(endpoint_value) if endpoint_value else None

                if item_endpoint:
                    llm_info_dict = {**item_endpoint, **item_type}
                    all_llms_list.append(llm_info_dict)
            return all_llms_list
        except Exception as e:
            self.__logger.error(f"Error getting all LLMs: {e}", exc_info=True)
            raise

    def update_llm(self, 
                   name, 
                   model=None, 
                   url=None, 
                   username=None, 
                   password=None, 
                   response_mime=None, 
                   system_message=None, 
                   prompt_mask=None, 
                   is_external = False,
                   stream_url = None,
                   http_stream_url = None,
                   fim_url = None):
        try:
            # Fetch the existing item
            value, metadata = self.__etcd.get(f"/llms/endpoints/{name}")
            existing_item = json.loads(value) if value else None

            if not existing_item:
                self.__logger.error(f"LLM with name {name} not found for update.", exc_info=True)
                return

            # Only update the provided fields
            update_fields = {
                "model": model,
                "url": url,
                "response_mime": response_mime,
                "system_message": system_message,
                "prompt_mask": prompt_mask,
                "is_external": is_external,
                "stream_url": stream_url if stream_url is not None else '',
                "http_stream_url": http_stream_url if http_stream_url is not None else '',
                "fim_url": fim_url if fim_url else None,
            }

            # Filter out None values
            update_fields = {k: v for k, v in update_fields.items() if v is not None}

            # Specifically handle username and password updates
            if username is not None and username != '':
                update_fields['username'] = username
            if password is not None and password != '':
                update_fields['password'] = password

            # Update the existing item with new values
            updated_item = {**existing_item, **update_fields}

            # Update the item in etcd
            self.__etcd.put(f"/llms/endpoints/{name}", json.dumps(updated_item))

        except Exception as e:
            self.__logger.error(f'Error updating LLM: {e}', exc_info=True)
            raise


    def delete_llm(self, name):
        try:
            # Delete item from etcd
            self.__etcd.delete(f"/llms/endpoints/{name}")
        except Exception as e:
            self.__logger.error(f"Error deleting LLM: {e}", exc_info=True)

    def get_llm_by_priority(self, type='text', priority=0):       
        try:
            type_value, type_metadata = self.__etcd.get(f"/llms/types/{type}/{priority}")
            item_type = json.loads(type_value) if type_value else None

            if not item_type:
                return None

            endpoint_value, endpoint_metadata = self.__etcd.get(f"/llms/endpoints/{item_type['name']}")
            item_endpoint = json.loads(endpoint_value) if endpoint_value else None

            if item_type and item_endpoint:
                llm = {**item_type, **item_endpoint}
                return llm
            return None
        except Exception as e:
            self.__logger.error(f"Error getting LLM for type {type}: {e}", exc_info=True)
            raise
    
    def get_llms_by_type(self, type):
        llms = []
        try:
            for type_value, type_metadata in self.__etcd.get_prefix(f"/llms/types/{type}/"):
                item_type = json.loads(type_value)
                
                endpoint_value, endpoint_metadata = self.__etcd.get(f"/llms/endpoints/{item_type['name']}")
                item_endpoint = json.loads(endpoint_value) if endpoint_value else None

                if item_type and item_endpoint:
                    llm = {**item_type, **item_endpoint}
                    llms.append(llm)
            return llms
        except Exception as e:
            self.__logger.error(f"Error getting LLM for type {type}: {e}", exc_info=True)
            raise
