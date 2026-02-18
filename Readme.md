# Airflow Multirepo Deploy plugin

Airflow plugin for deploying DAGs from multiple Git repository from Airflow webserver.

The plugin scans every folder in Airflow DAGs folder (without subfolders),
and check if it's a git repository. It's intended to be used in a scenario where DAGs are
stored in a single shared volume. The volume must be mounted in the webserver too.

It's been designed for scenarios where Airflow is deployed in a Kubernetes cluster,
and multiple teams deploy their DAGs from separate repos.

## Features

* Deploy DAGs from multiple Git repos
* See deployed commit for each environment
* Easily switch between branches

![](images/repos.png)
![](images/deployment.png)

## Installation

1) Install `gitpython` in your Airflow webserver
2) Clone this repo inside Airflow plugins folder
3) Configure your webserver to enable `git pull` on your DAGs repo (ssh keys, etc.)

## Usage

Clone your dag repos to the airflow DAGs folder.

### Airflow helm chart

To use this plugin with the official Airflow helm chart, you need to configure:
* `dags.persistence` to create a shared persistent volume
* `webserver.extraVolumes` and `webserver.extraVolumeMounts` to mount the volume in the webserver

### Configuration
Have a look at this configuration snippet and adjust it to your needs.
The only required part is the GitHub App configuration if you want to use GitHub App authentication.
If you don't configure it, the plugin will fall back to using SSH keys for authentication, which is also supported out of the box.

```
[multirepo_deploy]
# URL prefix for the deployment routes
url_prefix = deployment

# Path to the React app dist folder
react_app_dir = /path/to/plugin/ui/dist

# Optional post-deployment hook (Python callable)
# post_hook = mymodule.my_function

# Optional: restrict which branches can be deployed (comma-separated)
# allowed_branches = origin/main,origin/develop,origin/staging

# GitHub App Configuration (required for GitHub App authentication)
# To use GitHub App authentication, you need all three of these:

# 1. Your GitHub App ID (found in app settings)
gh_app_id = 123456

# 2. Base64-encoded private key for your GitHub App (PEM format)
#    Generate this from your GitHub App settings
gh_app_private_key = LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQo... (truncated for security)

# 3. Installation ID for your organization
#    Find this in the URL when you view the app installation:
#    https://github.com/organizations/YOUR_ORG/settings/installations/INSTALLATION_ID
gh_app_installation_id = 12345678

# Note: If these are not configured, only SSH key method will be available
```

### Authentication
While you should configure the Git authentication specific to your environment,
the plugin supports multiple SSH keys (like GitHub deployment keys) out of the box.
For a given repo , simply store the SSH key in a file `<repo_folder_name>.key`
in the parent folder of the repo.

### Requirements

The following Python packages are quired for the plugin to work:
```
# Git operations
GitPython>=3.1.0

# GitHub App authentication
PyJWT>=2.8.0
cryptography>=41.0.0  # Required by PyJWT for RSA keys
requests>=2.31.0
```
