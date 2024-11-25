import json
import logging
import os
import requests
from config.config import Config
import controllers.constants as constants
import concurrent.futures

from exception.exceptions import FimNotSupportedException
from liev_llm_manager.manager import get_manager
from requests.auth import HTTPBasicAuth as HTTPBasicAuthServer
from flask import request as flask_request


class DispatcherController:
    """
    DispatcherController manages LLM (Large Language Model) interactions,
    handling failover and multi-LLM requests.
    """

    def __init__(self) -> None:

        self.__config = Config('dispatcher')
        # Configure logging
        logging.basicConfig(
            level=self.__config.get('LOG_LEVEL', 'DEBUG'),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.__logger = logging.getLogger(__name__)

        # Initialize the LLM manager
        self.__manager = get_manager()

        # Initialize Toxicity
        self.__toxicity_filter = self.__str_to_bool(self.__config.get('TOXICITY_FILTER', 'false'))
        if (self.__toxicity_filter):
            self.__toxicity_message="This message contains toxic language and is not allowed.\nEsta mensagem contém linguagem tóxica e não é permitida.\nEste mensaje contiene lenguaje tóxico y no está permitido."
        else:
            self.__logger.warn('Toxicity filter is disabled! Counting only with model protections.')

    def get_response(self, data, auth, is_fim = False):
        """
        Processes a request to the dispatcher, managing LLM interactions and handling failovers.

        Args:
            data (dict): The request payload.
            auth (object): The authentication object.

        Returns:
            Tuple: Response content, status code, and response headers.
        """

        # Filter Toxicity
        if (self.__is_prompt_toxic(data, auth)):
            return self.__toxicity_message, 400

        # Whether the user wants the failover or not
        try_next_on_failure = data.get('try_next_on_failure', True)

        # Get llm name, if specified
        llm_name = data.get('llm_name', None)

        # Get the Function or Type from payload. They are synonym.
        type_str = data.get('function')  # For backward compatibility
        if type_str is None:
            type_str = data.get('type')  # New format

            # If Function/Type is not specified, set it for "detect" to enter the LLM Detection flow
            if type_str is None and llm_name is None:
                type_str = "detect"
            elif type_str is None and llm_name is not None:
                # If the user is specifiying the llm name, automatically disable the failover
                try_next_on_failure = False
        
        # The flag to control whether the response is processed
        processed = False

        # The flag indicating when a failover occurs. This will be returned in the Liev-Response-Is-Failover header in the end
        is_failover_response = False

        # Start searching the LLM for the type specified by the first priority
        current_priority = 1

        # An list of failed failover LLMs. This will be returned in the Liev-Response-Failed-Models header in the end
        failed_llms = []


        # If type is set to "detect", enter the prompt detection flow
        if type_str == "detect":
            self.__logger.debug('Type not informed. Prompt detection needed.')
            type_str = self.__detect_prompt(data, auth)

        # Declare a list of choosen llms that will be used
        chosen_llms = []

        # Get LLMs that will be used based on type and/or llm_name
        try:
            # If the payload contains the LLM name
            if llm_name:

                # And if the LLM wanted is 'all of them available by the type', 
                if llm_name == 'all':
                    # Put all the available LLMs for this type in the choosen_llms
                    chosen_llms = self.__manager.get_llms_by_type(type_str)
                    self.__logger.debug(f"Multi LLMs requested. Chosen LLMs are: {', '.join(map(lambda llm: llm['name'], chosen_llms))}")
                
                # Otherwise, put only the llm specified by name
                else:
                    try:
                        llm = self.__manager.get_llm_by_name(llm_name)
                        if llm is not None:
                            chosen_llms.append(llm)
                            self.__logger.debug(f"Chosen LLM is: {chosen_llms[0]['name']}")
                        elif llm is None and try_next_on_failure: 
                            chosen_llms.append(self.__manager.get_llm_by_priority(type_str, current_priority))
                            self.__logger.debug(f"Chosen LLM is: {chosen_llms[0]['name']}")
                        else:
                           raise Exception("LLM not found")
                    except Exception as e:
                        if llm is None and not try_next_on_failure:
                            self.__logger.error(f"Error calling {llm_name}: {e}. Won't trying failover")
                            return f"No LLMs were available to process the request. Won't trying failover. Error message: {str(e)}", response_code
                        else:
                            chosen_llms.append(self.__manager.get_llm_by_priority(type_str, current_priority))
                            self.__logger.debug(f"Chosen LLM is: {chosen_llms[0]['name']}")
                    

            # If the payload doesn't contain the LLM name, let's get from the manager the LLM in the current priority for the given type
            else:
                chosen_llms.append(self.__manager.get_llm_by_priority(type_str, current_priority))
                self.__logger.debug(f"Chosen LLM is: {chosen_llms[0]['name']}")
        except Exception as e:
            self.__logger.error(f'LLM Request: {flask_request.method} {flask_request.path} Type: {type_str}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
            self.__logger.error(f"Error getting next priority LLM: {e}", exc_info=True)
            return json.dumps("No LLMs were available to process the request"), 500

        # Starting the flow with single llm
        if len(chosen_llms) == 1:
            chosen_llm = chosen_llms[0]

            response_content = ''
            response_code = None

            # While I don't have an answer from an LLM
            while not processed:
                try:
                    # Call the LLM
                    response = self.__call_llm(chosen_llm, data, is_fim)

                    # Set the response type based on chosen llm information
                    response_mime = chosen_llm['response_mime']

                    # Get the response content and responde code
                    response_content = response.content
                    response_code = response.status_code

                    # If unsuccessful, raise
                    if response_code != 200:
                        raise Exception(f"Response code not successful: {response_code} {response_content}")

                    self.__logger.info(f'LLM Request: {flask_request.method} {flask_request.path} LLM_Name: {chosen_llm["name"]}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}, Request_Bytes: {len(response.request.body)}, Response_Bytes: {len(response.content)}, Response_Time: {response.elapsed.total_seconds()}')
                
                # Oops, got problems on calling the current LLM
                except Exception as e:

                    # If the user wants failover
                    if try_next_on_failure:

                        # Set the indicator that the response is already a failover
                        is_failover_response = True
                        self.__logger.error(f"Error calling {chosen_llm['name']}: {e}. Trying the next priority LLM for type {type_str}")
                        
                        # If the request is based just on the llm_name, there is no failover
                        if llm_name is not None:
                            current_priority = 1
                            llm_name = None
                        # Else, increment the current priority to try to get the next one
                        else:
                            current_priority += 1
                        
                        # Add the failed LLM to the failed list. This will be returned in the Liev-Response-Failed-Models header in the end
                        failed_llms.append(f"{chosen_llm['name']}({chosen_llm['model']})")
                        
                        # AGAIN, get the next priority LLM for the type 
                        try:
                            chosen_llm = self.__manager.get_llm_by_priority(type_str, current_priority)
                            self.__logger.debug(f"Chosen LLM is: {chosen_llm['name']}")

                            # Continue the "While not processed" loop ^^^
                            continue
                        except Exception as e:

                            # No LLMs were available. Return error.
                            self.__logger.error(f'LLM Request: {flask_request.method} {flask_request.path} Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
                            self.__logger.error(f"Error getting next priority LLM: {e}", exc_info=True)
                            return json.dumps("No LLMs were available to process the request"), 500
                        
                    # If the user doesn't want failover
                    else:
                        if response_code is None:
                            response_code = 500
                        # Return error
                        self.__logger.error(f"Error calling {chosen_llm['name']}: {e}. Won't trying failover")
                        return f"No LLMs were available to process the request. Won't trying failover. Error message: {str(e)}", response_code


                # I have an LLM response! Set processed true to skip the next priority iteration loop
                processed = True

                # Set response and headers
                response_headers = {
                    'Content-Type': response_mime,
                    'Liev-Response-Model': f"{chosen_llm['name']}({chosen_llm['model']})",
                    'Liev-Response-Is-Failover': is_failover_response,
                    'Liev-Response-Failed-Models': ",".join(failed_llms)
                }
                return response_content, response_code, response_headers

        # Start the flow with multi LLM responses
        else:
            # Multi LLM response handling

            # List for combined answers
            combined_answers = []
            combined_mime = 'application/json'
            
            # Start concurrent request for all wanted LLMs. Combining all the answerds
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_to_url = {executor.submit(self.__call_llm, chosen_llm, data): [chosen_llm, f'{flask_request.method}', f'{flask_request.path}', auth.current_user()] for chosen_llm in chosen_llms}
                successful_llms = []
                failed_llms = []
                
                for future in concurrent.futures.as_completed(future_to_url):
                    llm = future_to_url[future][0]
                    method = future_to_url[future][1]
                    path = future_to_url[future][2]
                    user = future_to_url[future][3]
                    
                    try:
                        data = future.result()
                        combined_answers.append(json.loads(f'{{"name":"{llm["name"]}({llm["model"]})", "response": {data.text}}}'))
                        successful_llms.append(f'{llm["name"]}({llm["model"]})')
                        self.__logger.info(f'LLM Request: {method} {path} LLM_Name: {llm["name"]}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}, Request_Bytes: {len(data.request.body)}, Response_Bytes: {len(data.text)}, Response_Time: {data.elapsed.total_seconds()}')
                    except Exception as exc:
                        self.__logger.error(f'LLM Request: {method} {path} LLM_Name: {llm["name"]}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
                        self.__logger.error(f"Error calling {llm['name']}: {exc}", exc_info=True)
                        failed_llms.append(f'{llm["name"]}({llm["model"]})')
                
                response_headers = {
                    'Content-Type': combined_mime,
                    'Liev-Response-Model': ','.join(map(lambda llm: llm, successful_llms)),
                    'Liev-Response-Is-Failover': 'False',
                    'Liev-Response-Failed-Models': ', '.join(map(lambda llm: llm, failed_llms))
                }
                return json.dumps(combined_answers), 200, response_headers

    def __call_llm(self, chosen_llm, data, is_fim = False):
        """
        Calls the specified LLM with the given data.
        Replaces system message and sets prompt mask, if defined in LLM endpoint configuration

        Args:
            chosen_llm (dict): The chosen LLM configuration.
            data (dict): The request payload.

        Returns:
            Response: The response from the LLM.
        """
        username = chosen_llm['username']
        password = chosen_llm['password']
        
        auth_server = HTTPBasicAuthServer(username, password)
        
        

        if not is_fim:
            address = chosen_llm['url']
            # Use the prompt mask, if defined in the LLM configuration
            if 'instruction' in data:
                data['instruction'] = self.__set_prompt_to_prompt_mask(data['instruction'], chosen_llm)

            # Use the default system message, if defined in the LLM configuration
            if 'system_message' in chosen_llm and len(chosen_llm['system_message']) > 0:
                data['system_msg'] = chosen_llm['system_message']

            response = requests.get(address, data=json.dumps(data), auth=auth_server)
        else:
            if 'fim_url' in chosen_llm:
                address = chosen_llm['fim_url']
                response = requests.get(address, data=json.dumps(data), auth=auth_server)
            else: 
                raise FimNotSupportedException()
        return response
    
    def __set_prompt_to_prompt_mask(self, prompt, chosen_llm):
        """
        Set the prompt in the prompt mask defined in the LLM Configuration

        Example:
        Prompt Mask: Generate Unit tests for the For the code. Code: %PROMPT%
        Prompt: <Program code>

        Args:
            prompt (str): The prompt received by the user
            chosen_llm (dict): The chosen LLM configuration.
        Returns:
            Response: The response from the LLM.
        """
        # Get the prompt mask - the original prompt will be masked with these instructions
        if ('prompt_mask' in chosen_llm and len(chosen_llm['prompt_mask']) > 0):
            prompt_mask = chosen_llm['prompt_mask']

            # Set the original prompt in the prompt mask
            return prompt_mask.replace('%PROMPT%', prompt)
        else:
            return prompt
        
    def __detect_prompt(self, data, auth):
        """
        Detects the type of prompt from the given data using the Default LLM for detect

        This method uses an LLM to categorize the prompt provided in the data. If the prompt type is successfully
        detected, it returns the detected type. If the type is not detected or any error occurs, it logs the error
        and returns a failure message.

        Args:
            data (dict): The input data containing the prompt instruction to be classified.

        Returns:
            str: The detected type of the prompt if successful.
            tuple: A JSON formatted error message and HTTP status code 500 if detection fails.

        Raises:
            Exception: If the detected type is not in the allowed list of types, an exception is raised.
        """
        try:
             # Get an LLM of type "detect" - capable of do prompt categorization. Usually codellama.
            detect_llm = self.__manager.get_llm_by_priority("detect", 1)
            self.__logger.debug(f"Chosen LLM is: {detect_llm['name']}")
            # The payload and parameters for prompt detection
            # WARNING: This payload is only used for the classification/detect task.
            data_detect = {
                "instruction": data.get('instruction'),
                "max_new_tokens": 512,
                "temperature": 0.1,
                "timeout": 60,
            }
            
            # Call The LLM
            response = self.__call_llm(detect_llm, data_detect)        
            self.__logger.info(f'LLM Request: {flask_request.method} {flask_request.path} LLM_Name: {detect_llm["name"]}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}, Request_Bytes: {len(response.request.body)}, Response_Bytes: {len(response.content)}, Response_Time: {response.elapsed.total_seconds()}')
            
            # Strip the detected type from extra chars, giving just the type word
            # Sets the type detected in the type_str variable to continue the flow to call the appropriate LLM
            type_str = response.text.replace("'", "").replace('"', '').strip().lower()
            
            # If the detected type is not in the constansts.allowed_detect_types, than the LLM was not able to detect. Raise Exception and stop.
            if type_str not in constants.allowed_detect_types:
                raise Exception("Could not detect type")
            
            self.__logger.debug(f"Type detected: {type_str}")
            return type_str
        except Exception as e:
            self.__logger.error(f'LLM Request: {flask_request.method} {flask_request.path} Type: detect, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
            self.__logger.error(f"Error calling {detect_llm['name']}: {e}", exc_info=True)
            return json.dumps("No LLMs were available to process the content detection. Try specifying type in payload"), 500
        
    def __is_prompt_toxic(self, data, auth):
        if (self.__toxicity_filter):
            try:
                # Get an LLM of type "toxicity"
                toxicity_llm = self.__manager.get_llm_by_priority("toxicity", 1)
                self.__logger.debug(f"Chosen LLM is: {toxicity_llm['name']}")
                # The payload and parameters for prompt detection
                # WARNING: This payload is only used for the classification/detect task.
                data_toxicity = {
                    "sentence": data.get('instruction'),
                }

                # Model Server Auth
                username = toxicity_llm['username']
                password = toxicity_llm['password']
        
                auth_server = HTTPBasicAuthServer(username, password)
                address = toxicity_llm['url']

                # Call The LLM
                response = requests.get(address, data=json.dumps(data_toxicity), auth=auth_server)        
                self.__logger.info(f'LLM Request: {flask_request.method} {flask_request.path} LLM_Name: {toxicity_llm["name"]}, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}, Request_Bytes: {len(response.request.body)}, Response_Bytes: {len(response.content)}, Response_Time: {response.elapsed.total_seconds()}')
                
                # Parse the boolean return
                bool_toxic = self.__str_to_bool(response.text.replace("'", "").replace('"', '').strip().lower())
                
                return bool_toxic
            except Exception as e:
                self.__logger.error(f'LLM Request: {flask_request.method} {flask_request.path} Type: detect, Application: {auth.current_user()["application"]}, User: {auth.current_user()["username"]}')
                self.__logger.error(f"Error calling {toxicity_llm['name']}: {e}", exc_info=True)
                return json.dumps("No LLMs were available to process toxicity. Try specifying type in payload"), 500

    def __str_to_bool(self, v):
        return v.lower() in ("yes", "true", "t", "1")