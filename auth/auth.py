import logging
import os
from flask import request
import jwt
import base64
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import json
from urllib.request import urlopen
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth
import yaml

from config.config import Config

"""
Class to helping switching between HTTP Basic Auth and OAuth SSO

Author: Erick Amaral / Inmetrics

"""
class AuthHelper():
    def __init__(self, mode):
        self.__config = Config('dispatcher')
        if mode not in ['basic','oauth']:
            raise Exception('Invalid auth mode.')
        self.__mode = mode
        self.__init_flask_auth()
        self.__logger = logging.getLogger("AuthHelper")
        

    def get_flask_auth(self):
        return self.__auth

    def __init_flask_auth(self):
        if self.__mode == 'basic':
            self.__auth = HTTPBasicAuth()
            self.__load_http_basic_users()
            self.__auth.verify_password_callback = self.__verify_password
            self.__auth.get_user_roles_callback = self.__get_user_roles_basic
        elif self.__mode == 'oauth':
            openid_config_url = self.__config.get('AUTH_OAUTH_OPENID_CONFIG_URL')
            self.__client_id = self.__config.get('AUTH_OAUTH_CLIENT_ID')
            self.__client_secret = self.__config.get('AUTH_OAUTH_CLIENT_SECRET')
            if None in (openid_config_url, self.__client_id, self.__client_secret):
                raise Exception('AUTH_OAUTH_OPENID_CONFIG_URL, AUTH_OAUTH_CLIENT_ID or AUTH_OAUTH_CLIENT_SECRET not defined!')
            self.__openid_config = json.loads(urlopen(openid_config_url).read())
            self.__jwks = json.loads(urlopen(self.__openid_config['jwks_uri']).read())
            self.__jwt_algos = self.__openid_config['id_token_signing_alg_values_supported']
            self.__auth = HTTPTokenAuth(scheme='Bearer')
            self.__auth.verify_token_callback = self.__verify_token
            self.__auth.get_user_roles_callback = self.__get_user_roles_oauth

    def __load_http_basic_users(self):
        with open("users.yaml") as f:
            self.__users = yaml.safe_load(f) 

    def __verify_password(self, username, password):
        """ Check username and password to allow access to the API when using basic auth"""
        if not (username and password):
            return False
        user = next((user for user in self.__users if user["username"] == username), None)
        if user==None:
            return False
        else:
            if user["password"] == password:
                return { 'username': username, 'application': None }
            else:
                return False
    
    def verify_password(self, username, password):
        return self.__verify_password(username, password)
    
    def __verify_token(self, token):
        """ Check token when using OAuth"""
        if not token:
            return False
        
        decoded_token = self.__token_is_valid(self.__client_id, token)
        # Validate the access token
        if not decoded_token:
            return False
        else:
            if 'preferred_username' in decoded_token:
                return { 'username': decoded_token['preferred_username'] , 'application' : None } # Return the client username, if it's a personal token
            elif 'azp' in decoded_token:
                if 'Liev-Client-Username' in request.headers:
                    #return f"{decoded_token['azp']}\{request.headers['Liev-Client-Username']}"
                    return { 'username': request.headers['Liev-Client-Username'], 'application' : decoded_token['azp'] }
                return { 'username': 'unknown' , 'application' : decoded_token['azp'] }  # Return Authorized Party ID, if it's a client application
            else:
               return False

    def __get_user_roles_basic(self, userinfo):
        user = next((user for user in self.__users if user["username"] == userinfo["username"]), None)
        return user['roles']
    
    def __get_user_roles_oauth(self, userinfo):
        token = request.headers.get('Authorization', '').split('Bearer ')[-1]
        decoded_token = self.__token_is_valid(self.__client_id, token)

        if 'preferred_username' in decoded_token:
            username_token = decoded_token['preferred_username']
        elif 'azp' in decoded_token:
            username_token = decoded_token['azp']
        else:
            raise Exception('Cannot obtain username or azp from decoded token')

        if userinfo['application'] == username_token or userinfo['username'] == username_token:
            # Get the roles from the property roles. Usually MS AD put roles inside this property
            if 'roles' in decoded_token:
                roles = decoded_token['roles']
            elif 'resource_access' in decoded_token:
                # But, Keycloak stores roles inside resource_access/<client-id>/roles
                roles = decoded_token['resource_access'][self.__client_id]['roles']
            else:
                raise Exception('Cannot get client roles from decoded token')
            return roles
        return None

    def __token_is_valid(self, client_id, token):
        try:
            # https://learn.microsoft.com/en-us/answers/questions/1463988/issues-with-token-format-in-azures-entra-id-servic
            issuer_url = self.__openid_config['issuer']
            audience = client_id

            unverified_header = jwt.get_unverified_header(token)
            rsa_key = self.__find_rsa_key(self.__jwks, unverified_header)
            public_key = self.__rsa_pem_from_jwk(rsa_key)
             
            decoded_token = jwt.decode(
                token,
                public_key,
                verify=True,
                algorithms=self.__jwt_algos,
                audience=audience,
                issuer=issuer_url,
                options={"verify_signature": True}
            )
            self.__logger.debug(f"Decoded token: {decoded_token}")

            return decoded_token
        except Exception as e:
            self.__logger.error(f"Error in _token_is_valid: {e}", exc_info=True)
            return False

    def __find_rsa_key(self, jwks, unverified_header):
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                return {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }

    def __ensure_bytes(self, key):
        if isinstance(key, str):
            key = key.encode('utf-8')
        return key


    def __decode_value(self, val):
        decoded = base64.urlsafe_b64decode(self.__ensure_bytes(val) + b'==')
        return int.from_bytes(decoded, 'big')


    def __rsa_pem_from_jwk(self, jwk):
        return RSAPublicNumbers(
            n=self.__decode_value(jwk['n']),
            e=self.__decode_value(jwk['e'])
        ).public_key(default_backend()).public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )