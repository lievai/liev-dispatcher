import boto3
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal
import logging
import os
from config.config import Config
from liev_llm_manager.exception.exception import LLMMissingRequiredFieldException
from liev_llm_manager.base_llm_manager import BaseLLMManager
from botocore.config import Config as BotoConfig

name = 'DynamoDBEndpointManager'
class DynamoDBEndpointManager(BaseLLMManager):
    def __init__(self):
        super().__init__()
        self.__config = Config('dispatcher')
        self.__logger = logging.getLogger("DynamoDBEndpointManager")
        self.__aws_access_key_id = self.__config.get('AWS_ACCESS_KEY_ID')
        self.__aws_secret_access_key = self.__config.get('AWS_SECRET_ACCESS_KEY')
        self.__region_name = self.__config.get('AWS_REGION')
        self.__endpoint_table_name = self.__config.get('AWS_ENDPOINT_TABLE_NAME')
        self.__type_table_name = self.__config.get('AWS_TYPE_TABLE_NAME')

        if None in (self.__aws_access_key_id, self.__aws_secret_access_key, self.__region_name, self.__endpoint_table_name, self.__type_table_name):
            raise Exception("If using LLM_MANAGER_IMPL='aws_dynamodb' you need to set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_TABLE_NAME, AWS_TYPE_TABLE_NAME and AWS_REGION env vars!")

        try:
            self.__dynamodb = boto3.resource('dynamodb', aws_access_key_id=self.__aws_access_key_id,
                                            aws_secret_access_key=self.__aws_secret_access_key,
                                            region_name=self.__region_name,
                                            config=BotoConfig(max_pool_connections=50))

            # Endpoint table
            self.__endpoint_table = self.__dynamodb.Table(self.__endpoint_table_name)

            # Type table
            self.__type_table = self.__dynamodb.Table(self.__type_table_name)

            # Check if tables already exist, create if not
            existing_tables = self.__dynamodb.meta.client.list_tables()['TableNames']
            if self.__endpoint_table_name not in existing_tables:
                self.__create_endpoint_table()
            if self.__type_table_name not in existing_tables:
                self.__create_type_table()

        except Exception as e:
            self.__logger.error(f"Error initializing DynamoDBEndpointManager: {e}", exc_info=True)

    def __create_endpoint_table(self):
        # Define table schema
        table = self.__dynamodb.create_table(
            TableName=self.__endpoint_table_name,
            KeySchema=[
                {'AttributeName': 'name', 'KeyType': 'HASH'},  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'name', 'AttributeType': 'S'},  # S for string
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        # Wait until the table is created
        table.meta.client.get_waiter('table_exists').wait(TableName=self.__endpoint_table_name)
        self.__logger.info('Endpoint table created successfully!')

    def __create_type_table(self):
        # Define table schema
        table = self.__dynamodb.create_table(
            TableName=self.__type_table_name,
            KeySchema=[
                {'AttributeName': 'type', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'name', 'KeyType': 'RANGE'},  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'type', 'AttributeType': 'S'},
                {'AttributeName': 'name', 'AttributeType': 'S'},
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        # Wait until the table is created
        table.meta.client.get_waiter('table_exists').wait(TableName=self.__type_table_name)
        self.__logger.info('Type table created successfully!')

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
            # Create item in the endpoint table
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
            
            self.__endpoint_table.put_item(Item=endpoint_data)

        except Exception as e:
            self.__logger.error(f'Error creating LLM: {e}', exc_info=True)
    
    def create_llm_type(self, name, type, priority):
        try:
            # Fetch all items of the given type
            response = self.__type_table.query(
                KeyConditionExpression=Key('type').eq(type)
            )
            items_type = response.get("Items", [])
            serialized_items_type = self.__convert_decimal_to_numbers(items_type)

            # If priority is 0, set it to the highest available
            if priority == 0:
                max_priority = max([item['priority'] for item in serialized_items_type], default=0)
                priority = max_priority + 1

            # Ensure priority doesn't exceed the last available priority
            max_priority = max([item['priority'] for item in serialized_items_type], default=0)
            if priority > max_priority + 1:
                priority = max_priority + 1

            # Update priorities
            for item in serialized_items_type:
                if item['priority'] >= priority:
                    item['priority'] += 1
                    self.__type_table.put_item(Item=item)

            # Create the new item with the desired priority
            type_data = {
                "type": type,
                "name": name,
                "priority": priority
            }
            self.__type_table.put_item(Item=type_data)
        except Exception as e:
            self.__logger.error(f'Error creating LLM type: {e}', exc_info=True)


    def update_llm_type(self, name, type, priority):
        # In Dynamo, create again will replace
        self.create_llm_type(name, type, priority)
    
    def delete_llm_type(self, name, type):
        try:
            # Delete the item from the type table
            self.__type_table.delete_item(
                Key={
                    "type": type,
                    "name": name
                }
            )
        except Exception as e:
            self.__logger.error(f"Error deleting LLM type: {e}", exc_info=True)
        
    def get_llm_by_name(self, name, type=None):
        try:
            if type is not None:
                response = self.__type_table.query(
                    KeyConditionExpression=Key('type').eq(type) & Key('name').eq(name)
                )
                items_type = response.get("Items", [])
                serialized_items_type = self.__convert_decimal_to_numbers(items_type)
                item_type = serialized_items_type[0] if serialized_items_type else None

                response = self.__endpoint_table.query(
                    KeyConditionExpression=Key('name').eq(name)
                )
                items_endpoint = response.get("Items", [])
                item_endpoint = items_endpoint[0] if items_endpoint else None

                if item_type and item_endpoint:
                    llm = {**item_type, **item_endpoint}
                    return llm
                return None
            else:
                response = self.__endpoint_table.query(
                    KeyConditionExpression=Key('name').eq(name)
                )
                items_endpoint = response.get("Items", [])
                item_endpoint = items_endpoint[0] if items_endpoint else None

                return item_endpoint
        except Exception as e:
            self.__logger.error(f"Error getting LLM by name: {e}", exc_info=True)
            raise

    def get_all_llms(self):
        try:
            response = self.__endpoint_table.scan()
            items_type = response.get("Items", [])
            serialized_items_type = self.__convert_decimal_to_numbers(items_type)

            return serialized_items_type
        except Exception as e:
            self.__logger.error(f"Error getting all LLMs: {e}", exc_info=True)
            raise
            
    def get_all_llms_and_types(self):
        try:
            all_llms_list = []
            response = self.__type_table.scan()
            items_type = response.get("Items", [])
            serialized_items_type = self.__convert_decimal_to_numbers(items_type)

            response = self.__endpoint_table.scan()
            items_endpoint = response.get("Items", [])
            serialized_items_endpoint = self.__convert_decimal_to_numbers(items_endpoint)
            for item_type in serialized_items_type:
                for item_endpoint in serialized_items_endpoint:
                        if item_type['name'] == item_endpoint['name']:
                          llm_info_dict = {**item_endpoint, **item_type}
                          #llm_info_dict['type'] = type_list['type']
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
                   is_external=False,
                   stream_url = None,
                   http_stream_url = None,
                   fim_url = None):
        try:
            # Fetch the existing item
            response = self.__endpoint_table.get_item(Key={'name': name})
            existing_item = response.get('Item')

            if not existing_item:
                self.__logger.error(f"LLM with name {name} not found for update.", exc_info=True)
                return

            # Only update the provided fields
            update_fields = {
                'model': model,
                'url': url,
                'response_mime': response_mime,
                'system_message': system_message,
                'prompt_mask': prompt_mask,
                'is_external': is_external,
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

            # Update the item in the table
            self.__endpoint_table.put_item(Item=updated_item)

        except Exception as e:
            self.__logger.error(f'Error updating LLM: {e}', exc_info=True)
            raise


    def delete_llm(self, name):
        try:
            # Delete item from the endpoint table
            self.__endpoint_table.delete_item(Key={"name": name})
        except Exception as e:
            self.__logger.error(f"Error deleting LLM: {e}", exc_info=True)

    def get_llm_by_priority(self, type='text', priority=0):       
        try:
            response = self.__type_table.query(
                KeyConditionExpression=Key('type').eq(type)
            )
            items_type = response.get("Items", [])
            serialized_items_type = self.__convert_decimal_to_numbers(items_type)
            item_type = next((item for item in serialized_items_type if item['priority'] == priority), None)

            response = self.__endpoint_table.query(
                KeyConditionExpression=Key('name').eq(item_type['name'])
            )
            items_endpoint = response.get("Items", [])
            item_endpoint = items_endpoint[0] if items_endpoint else None

            if item_type and item_endpoint:
                llm = {**item_type, **item_endpoint}
                return llm
            return None
        except Exception as e:
            self.__logger.error(f"Error getting LLM for type {type}: {e}", exc_info=True)
            #return None
            raise
    
    def get_llms_by_type(self, type):
        llms = []
        try:
            response = self.__type_table.query(
                KeyConditionExpression=Key('type').eq(type)
            )
            items_type = response.get("Items", [])
            serialized_items_type = self.__convert_decimal_to_numbers(items_type)
            
            for item_type in serialized_items_type:
                response = self.__endpoint_table.query(
                    KeyConditionExpression=Key('name').eq(item_type['name'])
                )
                items_endpoint = response.get("Items", [])
                item_endpoint = items_endpoint[0] if items_endpoint else None

                if item_type and item_endpoint:
                    llm = {**item_type, **item_endpoint}
                    llms.append(llm)
            return llms
        except Exception as e:
            self.__logger.error(f"Error getting LLM for type {type}: {e}", exc_info=True)
            #return None
            raise
        
    def __convert_decimal_to_numbers(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        elif isinstance(obj, list):
            return [self.__convert_decimal_to_numbers(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: self.__convert_decimal_to_numbers(value) for key, value in obj.items()}
        return obj
