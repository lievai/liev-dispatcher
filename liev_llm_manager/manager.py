import importlib
import os

from config.config import Config

config = Config('dispatcher')
def get_manager():
    impl = config.get('LLM_MANAGER_IMPL', 'endpoints_yaml')
    module = importlib.import_module('liev_llm_manager.'+impl)
    class_name = getattr(module, "name", None)
    Manager = getattr(module, class_name,None)
    if Manager is None:
        raise Exception(f"No manager found for {impl}")
    else:
        return Manager()