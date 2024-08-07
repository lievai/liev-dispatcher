import yaml
from liev_llm_manager.base_llm_manager import BaseLLMManager

name = 'YAMLEndpointManager'
class YAMLEndpointManager(BaseLLMManager):
    
    def __new__(cls):
        with open("endpoints.yaml") as f:
            cls.__endpoints = yaml.safe_load(f)
            cls.__llms = cls.__endpoints['llms']
            cls.__types = cls.__endpoints['types']
        return super().__new__(cls)

    def create_llm(self, name, model, url, username, password, response_mime, system_message='', prompt_mask='', is_external = False):
        raise NotImplementedError("LLM creation is not available through YAMLEndpointManager. Use the config files!")


    def get_llm_by_name(self, name, type=None):
        llm = None
        if (type is None):
            for l in self.__llms:
                if l['name'] == name:
                    llm = l
            if not llm:
                raise Exception(f"No LLM available for name {name}")
        else:
            for l in self.get_all_llms_and_types():
                if l['type'] == type and l['name'] == name:
                    llm = l
            if not llm:
                raise Exception(f"No LLM available for name {name} and type {type}")
        return llm
    
    def create_llm_type(self, name, type, priority):
        raise NotImplementedError("LLM creation is not available through YAMLEndpointManager. Use the config files!")
    
    def update_llm_type(self, name, type, priority, is_external = False):
        raise NotImplementedError("LLM creation is not available through YAMLEndpointManager. Use the config files!")

    def delete_llm_type(self, name, type):
        raise NotImplementedError("LLM creation is not available through YAMLEndpointManager. Use the config files!")

    def get_all_llms_and_types(self):
        all_llms_list = []
        for type_list in self.__types:
            for llm_type_list in type_list['llms']:
                for llm_list in self.__llms:
                    if llm_list['name'] == llm_type_list['name']:
                        llm_info_dict = {**llm_type_list, **llm_list}
                        llm_info_dict['type'] = type_list['type']
                        all_llms_list.append(llm_info_dict)
        return all_llms_list

    def get_all_llms(self):
        return self.__endpoints['llms']
    
    def update_llm(self, name, model, url, username, password, response_mime, system_message='', prompt_mask=''):
        raise NotImplementedError("LLM deletion is not available through YAMLEndpointManager. Use the config files!")

    def delete_llm(self, name):
        raise NotImplementedError("LLM deletion is not available through YAMLEndpointManager. Use the config files!")


    def get_llm_by_priority(self, type='text', priority = 0):
        llm = None
        for l in self.get_all_llms_and_types():
            if l['type'] == type and l['priority'] == priority:
                llm = l
        if not llm:
            raise Exception(f"No LLM available for type {type}")
        return llm
    

    def get_llms_by_type(self, type):
        llms = []
        for l in self.get_all_llms_and_types():
            if l['type'] == type :
                llms.append(l)
        if len(llms) == 0:
            raise Exception(f"No LLM available for type {type}")
        return llms