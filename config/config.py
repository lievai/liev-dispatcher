import os
import etcd3

class Config:
    """
    Config class to handle configuration settings based on the mode specified in the environment variable CONFIG_MODE.
    If CONFIG_MODE is 'local', it uses LocalConfig to fetch configurations from environment variables.
    Otherwise, it uses EtcdConfig to fetch configurations from an etcd server.
    """

    def __init__(self, client_id=None):
        """
        Initializes the Config class based on the mode specified in the environment variable CONFIG_MODE.
        
        Parameters:
        id (str, optional): Identifier used for EtcdConfig initialization. Defaults to None.
        """
        self.__mode = os.getenv('CONFIG_MODE', 'local')
        if self.__mode == 'local':
            self.__config = LocalConfig()
        elif self.__mode == 'etcd':
            self.__config = EtcdConfig(client_id)

    def get(self, key: str, default: str = None):
        return self.__config.get(key, default)

    def put(self, key: str, value: str):
        self.__config.put(key, value)

    def drop(self, key: str):
        self.__config.drop(key)

class LocalConfig:
    """
    LocalConfig class to fetch configuration settings from environment variables.
    """

    def get(self, key: str, default: str = None):
        """
        Fetches the value of the specified key from environment variables.
        
        Parameters:
        key (str): The key to fetch from environment variables.
        default (str, optional): The default value to return if the key is not found. Defaults to None.
        
        Returns:
        str: The value of the key from environment variables or the default value if the key is not found.
        """
        return os.getenv(key, default)

class EtcdConfig:
    """
    EtcdConfig class to fetch configuration settings from an etcd server.
    """

    def __init__(self, client_id):
        """
        Initializes the EtcdConfig class by connecting to the etcd server using the host and port specified in environment variables.
        
        Parameters:
        id (str): Identifier used for initialization.
        """

        if client_id is None:
            raise Exception('EtcdConfig must have a client id') 
        self._client = etcd3.client(os.getenv('ETCD_HOST', 'localhost'), os.getenv('ETCD_PORT', '2379'))
        self._client_id = client_id

    def get(self, key: str, default: str = None):
        """
        Fetches the value of the specified key from the environment variables or etcd server.
        
        Parameters:
        key (str): The key to fetch from the environment variables or etcd server.
        default (str, optional): The default value to return if the key is not found. Defaults to None.
        
        Returns:
        str: The value of the key from the environment variables or etcd server or the default value if the key is not found.
        """
        # First, check if the key is set as an environment variable
        value = os.getenv(key)
        if value is not None:
            return value
        
        # If not found in environment variables, check in etcd
        etcd_value = self._client.get(f"/{self._client_id}/{key}")[0]
        if etcd_value is not None:
            return etcd_value.decode('utf-8')
        
        # If not found in etcd, return the default value
        return default

    def put(self, key: str, value: str):
        """
        Sets the value of the specified key in the etcd server.
        
        Parameters:
        key (str): The key to set in the etcd server.
        value (str): The value to set for the specified key.
        """
        self._client.put(f"/{self._client_id}/{key}", value)

    def drop(self, key: str):
        """
        Removes the specified key from the etcd server.
        
        Parameters:
        key (str): The key to remove from the etcd server.
        """
        self._client.delete(f"/{self._client_id}/{key}")
