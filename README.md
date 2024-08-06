# Liev Dispatcher

Liev Dispatcher is the Liev Core component used for the interactions with Large Language Models (LLMs). It handles failover and multi-LLM requests, processes toxicity filtering, and supports prompt detection. The dispatcher is built to be integrated into a Flask application.

## Features

- **Multi-LLM Request Handling:** Manages interactions with multiple LLMs based on user-defined priorities and configurations.
- **Failover Support:** Automatically switches to alternate LLMs if the primary one fails, with configurable failover options.
- **Toxicity Filtering:** Filters out toxic content based on configurable settings.
- **Prompt Detection:** Detects the type of prompt if not explicitly specified, using a default LLM for detection.


The Liev Dispatcher is the front component for LLM Model Servers interaction. You need one or more Liev Core Model servers to properly run the Dispatcher:

```
______________________
|                     |----------------------> | Liev Model Server A| 
| The Liev Dispatcher |----------------------> | Liev Model Server B|
|_____________________|----------------------> | Liev Model Server N|


```

## Installation

### Environment Variables

#### Standard:

| Variable  | Description |Values | Default |
| ------------- |-------------|-------------|-------------|
| LOG_LEVEL     | Python logging level |CRITICAL, ERROR, WARNING, INFO, DEBUG      |INFO    |
| AUTH_MODE      | Auth mechanism used to authenticate users     | basic,oauth | basic|
| AUTH_LLM_USER_ROLE   | Name of the role used to list LLMs and call them    | User defined value| LLM.User|
| AUTH_LLM_ADMIN_ROLE   |  Name of the role used to manage LLMs and call them      | User defined value| LLM.Admin|
| LLM_MANAGER_IMPL   |  Name of the management backend database engine to use     | endpoints_yaml, aws_dynamodb, etcd| endpoints_yaml|
| TOXICITY_FILTER | Whether to use Toxicity Filter. Toxicity Model Server is needed | TRUE, FALSE | FALSE |


#### OAuth Configuration:
These must be used when AUTH_MODE=oauth

| Variable  | Description |
| ------------- |-------------|
| AUTH_OAUTH_OPENID_CONFIG_URL     | The .well-known/openid-configuration endpoint  |
| AUTH_OAUTH_CLIENT_ID     | The OAuth client id  |
| AUTH_OAUTH_CLIENT_SECRET     | The OAuth client secret  |

#### Endpoint Management

Liev Dispatcher supports currently 3 modes of endpoint management backend (AKA database)
New implementations can be created in the liev_llm_folder, extending the base class. The value passed to the LLM_MANAGER_IMPL is the Python filename of the implementation

| LLM_MANAGER_IMPL  variable | Description |
| ------------- |-------------|
| endpoints_yaml     | The endpoints.yaml file (default)  |
| aws_dynamodb     | AWS DynamoDB - requires  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and AWS_REGION env variables to be set. IAM permissions to create tables and write values are needed |
| etcd     | ETCD backend. Required ETCD_HOST and ETCD_PORT env variables to be set  |

#### Config Management

Liev Dispatcher supports also ETCD as the config backend. Instead of using env variables, the Config class will search the values in the ETCD database to get configurations
| Variable  | Description |
| ------------- |-------------|
| CONFIG_MODE     | The Config mode to be used. When 'local', env variables will be used. When 'etcd', ETCD backend will be used. But if a variable is set in the env, it will override the ETCD value. Default: local   |
| ETCD_HOST     | The hostname of the ETCD backend   |
| ETCD_PORT     | The port of the ETCD backend   |

# Running

#### Simple standalone - You may create a venv in you preferred way
```
$ pip install -r requirements.txt
$ sh start_dispatcher_gunicorn.sh
```

#### Docker - There is a Dockerfile for image building
```
$ docker build -t liev-dispatcher .
$ docker run -d liev-dispatcher
```
# User Management

Liev provides a simple users.yaml file to put down users, passwords and set roles.
But if OAuth is in use, this file is ignored - and SSO Authentication and role management comes in.

# Usage

A sample Jupter Notebook is provided to call the Dispatcher and the jupyter directory

# Credits

- Adriano Lima and Cleber Marques (Inmetrics) - creators of the first version of Dispatcher
- Erick Amaral (Inmetrics) - Developed Fallback/failover mechanism, prompt detection, SSO integration, DynamoDB and ETCD backend integrations
- Rafael Nakata and João Pedro Aras (USP) - Socket.io implementation for streaming

