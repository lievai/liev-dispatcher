# Base LLM Manager abstract class
# 2024 - Erick Amaral - Inmetrics

from abc import ABC, abstractmethod

"""Base LLM Manager, from where all pluggable persistent databases will be derived"""

class BaseLLMManager():

    @abstractmethod
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
                    http_stream_url = None):
        pass

    @abstractmethod
    def create_llm_type(self, name, type, priority):
        pass
    
    @abstractmethod
    def update_llm_type(self, name, type, priority):
        pass

    @abstractmethod
    def delete_llm_type(self, name, type):
        pass

    @abstractmethod
    def get_llm_by_name(self, name, type):
        pass

    @abstractmethod
    def get_all_llms(self):
        pass

    @abstractmethod
    def get_all_llms_and_types(self):
        pass

    @abstractmethod
    def update_llm(self, 
                   name, 
                   model, 
                   url, 
                   username, 
                   password, 
                   response_mime, 
                   system_message,
                   prompt_mask, 
                   is_external = False,
                   stream_url = None,
                   http_stream_url = None):
        pass

    @abstractmethod
    def delete_llm(self, name):
        pass

    @abstractmethod
    def get_llm_by_priority(self, type='text', priority=0):       
        pass
    
    @abstractmethod
    def get_llms_by_type(self, type):
        pass


