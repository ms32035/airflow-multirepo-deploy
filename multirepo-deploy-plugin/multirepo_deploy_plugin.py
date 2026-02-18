import base64
import importlib
import mimetypes
import os
import stat
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jwt
import requests
from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from git import GitCommandError, Repo
from git.exc import InvalidGitRepositoryError
from starlette.staticfiles import StaticFiles

mimetypes.add_type("application/javascript", ".cjs")

DAGS_FOLDER = conf.get("core", "dags_folder")
REACT_APP_DIR = conf.get("multirepo_deploy", "react_app_dir", fallback=Path(__file__).parent / "ui" / "dist")
URL_PREFIX = conf.get("multirepo_deploy", "url_prefix", fallback="deployment")

# GitHub App configuration - strip and validate
_gh_app_private_key_b64 = conf.get("multirepo_deploy", "gh_app_private_key", fallback="").strip()
_gh_app_installation_id = conf.get("multirepo_deploy", "gh_app_installation_id", fallback="").strip()

GH_APP_ID = conf.get("multirepo_deploy", "gh_app_id", fallback="").strip()
GH_APP_PRIVATE_KEY = base64.b64decode(_gh_app_private_key_b64).decode() if _gh_app_private_key_b64 else None
GH_APP_INSTALLATION_ID = int(_gh_app_installation_id) if _gh_app_installation_id else None


@dataclass
class RepoMeta:
    folder: str
    remotes: list
    active_branch: str
    sha: str
    commit_message: str
    author: str
    committed_date: int
    local_branches: list
    remote_branches: list
    repo: Repo

    @classmethod
    def from_repo(cls, repo: Repo, folder: str):
        try:
            active_branch = repo.active_branch.name
        except TypeError:
            active_branch = None

        try:
            sha = repo.head.commit.hexsha
            commit_message = repo.head.commit.message
            author = repo.head.commit.author.name
            committed_date = repo.head.commit.committed_date
        except ValueError:
            sha = None
            commit_message = None
            author = None
            committed_date = None

        if not repo.remotes:
            remote_branches = []
        elif "origin" in [rem.name for rem in repo.remotes]:
            remote_branches = [ref.name for ref in repo.remotes.origin.refs if "HEAD" not in ref.name]
        else:
            remote_branches = []

        return cls(
            folder=folder,
            remotes=[(rem.name, rem.url) for rem in repo.remotes],
            active_branch=active_branch,
            sha=sha,
            commit_message=commit_message,
            author=author,
            committed_date=committed_date,
            local_branches=[brn.name for brn in repo.branches],
            remote_branches=remote_branches,
            repo=repo,
        )

    @property
    def committed_date_str(self):
        return (
            datetime.fromtimestamp(self.committed_date).strftime("%Y-%m-%d %H:%M:%S") if self.committed_date else None
        )


def get_post_hook():
    callable_name = conf.get("multirepo_deploy", "post_hook", fallback=None)
    if not callable_name:
        return None
    module_name, callable_name = callable_name.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, callable_name)


def _create_github_askpass(token: str, folder: str) -> str:
    """Write a GIT_ASKPASS script that outputs the GitHub token"""
    # Sanitise folder name for use in path
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in folder)
    script_path = f"/tmp/git-askpass-{safe_name}.py"
    Path(script_path).write_text(f'#!/usr/bin/env python3\nprint("{token}")\n')
    os.chmod(script_path, stat.S_IRWXU)
    return script_path


def _git_env(dags_folder, folder: str) -> dict:
    """Get git environment variables including SSH key or GitHub App token"""
    env = {}

    # SSH key stored as a file: {dags_folder}/{folder}.key
    git_identity_file = Path(dags_folder).joinpath(f"{folder}.key")
    if git_identity_file.exists():
        env["GIT_SSH_COMMAND"] = f"ssh -i {git_identity_file} -o StrictHostKeyChecking=no"

    # GitHub App token via ASKPASS (works in non-interactive / containerised envs)
    github_marker = Path(dags_folder).joinpath(f"{folder}.github")
    if github_marker.exists():
        try:
            token = _get_github_app_token()
            env["GIT_ASKPASS"] = _create_github_askpass(token, folder)
            env["GIT_USERNAME"] = "x-access-token"
            env["GIT_TERMINAL_PROMPT"] = "0"
        except Exception:
            pass  # git operation will fail with a meaningful error

    return env


def _load_repo(path, folder) -> RepoMeta | bool:
    try:
        return RepoMeta.from_repo(Repo(path), folder)
    except InvalidGitRepositoryError:
        return False


class _GitHubTokenCache:
    """Singleton cache for the GitHub App installation access token"""

    _instance: "_GitHubTokenCache | None" = None

    def __new__(cls) -> "_GitHubTokenCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._token = None
            cls._instance._expires_at = 0
        return cls._instance

    def get(self, buffer_secs: int = 300) -> str | None:
        now = int(time.time())
        if self._token and self._expires_at > now + buffer_secs:
            return self._token
        return None

    def set(self, token: str, expires_at: int) -> None:
        self._token = token
        self._expires_at = expires_at


_token_cache = _GitHubTokenCache()

# Module-level sentinel for File upload parameter (avoids B008 linting warning)
_SSH_KEY_UPLOAD: UploadFile = File(...)


app = FastAPI()
app.mount(
    "/multirepo-deploy-ui",
    StaticFiles(directory=REACT_APP_DIR, html=True),
    name="multirepo-deploy-ui",
)


@app.get("/api/repos", response_class=JSONResponse)
async def list_repos_api():
    repos = []
    for f in Path(DAGS_FOLDER).iterdir():
        if f.is_dir() and f.name != ".git":
            repo = _load_repo(f, f.name)
            if repo:
                repos.append(
                    {
                        "folder": repo.folder,
                        "active_branch": repo.active_branch,
                        "committed_date_str": repo.committed_date_str,
                        "sha": repo.sha,
                        "author": repo.author,
                        "commit_message": repo.commit_message,
                        "remotes": repo.remotes,
                        "local_branches": repo.local_branches,
                        "remote_branches": repo.remote_branches,
                    }
                )

    # Sort repos alphabetically by folder name
    repos.sort(key=lambda r: r["folder"].lower())

    return {"repos": repos}


@app.get("/api/status/{folder:path}", response_class=JSONResponse)
async def repo_status_api(folder: str):
    repo_meta = _load_repo(Path(DAGS_FOLDER).joinpath(folder), folder)
    if not repo_meta:
        return JSONResponse({"error": "Repository not found"}, status_code=404)

    git_env = _git_env(DAGS_FOLDER, folder)
    errors = []

    # Fetch remote changes
    for rem in repo_meta.repo.remotes:
        try:
            rem.fetch(prune=True, env=git_env)
        except GitCommandError as gexc:
            errors.append(str(gexc))

    # Get allowed branches
    allowed_branches = conf.get("multirepo_deploy", "allowed_branches", fallback=None)
    if allowed_branches:
        branch_choices = [brn for brn in repo_meta.remote_branches if brn in allowed_branches.split(",")]
    else:
        branch_choices = repo_meta.remote_branches

    selected_branch = f"origin/{repo_meta.active_branch}" if repo_meta.active_branch else ""

    return {
        "repo": {
            "folder": repo_meta.folder,
            "active_branch": repo_meta.active_branch,
            "committed_date_str": repo_meta.committed_date_str,
            "sha": repo_meta.sha,
            "author": repo_meta.author,
            "commit_message": repo_meta.commit_message,
            "remotes": repo_meta.remotes,
            "local_branches": repo_meta.local_branches,
            "remote_branches": repo_meta.remote_branches,
        },
        "form": {"branches": branch_choices, "selected": selected_branch},
        "errors": errors if errors else None,
    }


@app.post("/deploy/{folder:path}")
async def deploy_repo(request: Request, folder: str, branches: str = Form(...)):
    repo = Repo(path=Path(DAGS_FOLDER).joinpath(folder))
    new_branch = branches
    new_local_branch = "/".join(new_branch.split("/")[1:])
    git_env = _git_env(DAGS_FOLDER, folder)

    try:
        repo.git.checkout(new_local_branch, env=git_env)
        repo.remotes.origin.fetch(env=git_env)
        repo.git.reset("--hard", f"origin/{new_local_branch}", env=git_env)
        post_hook = get_post_hook()
        if post_hook:
            post_hook(Path(DAGS_FOLDER).joinpath(folder))
    except (GitCommandError, Exception) as exc:
        error_message = traceback.format_exception(exc)

        return JSONResponse({"error": error_message}, status_code=400)

    return JSONResponse({"success": "Deployment successful"})


def _get_github_app_token():
    """Generate a JWT for GitHub App and get an installation access token with caching"""
    # Return cached token if still valid (5-minute buffer)
    cached = _token_cache.get()
    if cached:
        return cached

    now = int(time.time())

    if not all([GH_APP_ID, GH_APP_PRIVATE_KEY, GH_APP_INSTALLATION_ID]):
        missing = []
        if not GH_APP_ID:
            missing.append("gh_app_id")
        if not GH_APP_PRIVATE_KEY:
            missing.append("gh_app_private_key")
        if not GH_APP_INSTALLATION_ID:
            missing.append("gh_app_installation_id")
        raise ValueError(f"GitHub App credentials not fully configured. Missing: {', '.join(missing)}")

    private_key = GH_APP_PRIVATE_KEY

    # Generate JWT — iss must be an integer (passing a string triggers HMAC key-length warnings)
    payload = {
        "iat": now,
        "exp": now + (10 * 60),  # JWT expires in 10 minutes
        "iss": GH_APP_ID,
    }

    jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

    # Get installation access token
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = requests.post(
        f"https://api.github.com/app/installations/{GH_APP_INSTALLATION_ID}/access_tokens", headers=headers
    )

    if response.status_code != 201:  # noqa: PLR2004
        raise Exception(f"Failed to get installation token (status {response.status_code}): {response.text}")

    token_data = response.json()
    token = token_data["token"]
    expires_at_str = token_data.get("expires_at")  # e.g., "2024-01-01T12:00:00Z"

    # Parse expiry time or default to 1 hour from now
    if expires_at_str:
        expires_at = int(datetime.fromisoformat(expires_at_str.replace("Z", "+00:00")).timestamp())
    else:
        expires_at = now + 3600  # 1 hour default

    _token_cache.set(token, expires_at)
    return token


@app.get("/api/repos/github-available", response_class=JSONResponse)
async def github_available():
    """Check if GitHub App authentication is configured"""
    is_available = all([GH_APP_ID, GH_APP_PRIVATE_KEY, GH_APP_INSTALLATION_ID])

    config_status = {
        "gh_app_id": "configured" if GH_APP_ID else "missing",
        "gh_app_private_key": "configured" if GH_APP_PRIVATE_KEY else "missing",
        "gh_app_installation_id": "configured" if GH_APP_INSTALLATION_ID else "missing",
    }

    return {
        "available": is_available,
        "app_id": GH_APP_ID if GH_APP_ID else None,
        "config_status": config_status,
    }


@app.get("/api/repos/github-list", response_class=JSONResponse)
async def list_github_repos():
    """List GitHub repos accessible to the app that aren't already cloned"""
    try:
        token = _get_github_app_token()

        # Get list of already cloned repos
        existing_repos = set()
        for f in Path(DAGS_FOLDER).iterdir():
            if f.is_dir() and f.name != ".git":
                repo = _load_repo(f, f.name)
                if repo:
                    existing_repos.add(f.name)

        # List installation repositories with pagination
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.json"}

        all_repos = []
        page = 1
        per_page = 100  # Max allowed by GitHub API

        while True:
            response = requests.get(
                "https://api.github.com/installation/repositories",
                headers=headers,
                params={"per_page": per_page, "page": page},
            )

            if response.status_code != 200:  # noqa: PLR2004
                error_msg = f"Failed to list repositories (status {response.status_code}): {response.text}"
                return JSONResponse({"error": error_msg}, status_code=response.status_code)

            response_data = response.json()
            repos_batch = response_data.get("repositories", [])

            if not repos_batch:
                break

            all_repos.extend(repos_batch)

            # Check if we've fetched all repos
            total_count = response_data.get("total_count", 0)
            if len(all_repos) >= total_count:
                break

            page += 1

        # Filter out already cloned repos
        available_repos = [
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "clone_url": repo["clone_url"],
                "description": repo["description"],
            }
            for repo in all_repos
            if repo["name"] not in existing_repos
        ]

        # Sort repositories by name
        available_repos.sort(key=lambda r: r["name"].lower())

        return {
            "repos": available_repos,
            "total_repos": len(all_repos),
            "existing_repos": len(existing_repos),
            "available_repos": len(available_repos),
        }

    except ValueError as exc:
        # Configuration error
        return JSONResponse({"error": f"Configuration error: {str(exc)}"}, status_code=500)
    except FileNotFoundError as exc:
        # Private key file not found
        return JSONResponse({"error": f"Private key file error: {str(exc)}"}, status_code=500)
    except Exception as exc:
        return JSONResponse({"error": f"Unexpected error: {str(exc)}"}, status_code=500)


@app.post("/api/repos/add-ssh", response_class=JSONResponse)
async def add_repo_ssh(
    repo_url: str = Form(...),
    folder_name: str = Form(...),
    ssh_key: UploadFile = _SSH_KEY_UPLOAD,
):
    """Add a repository using SSH authentication"""
    folder_path = Path(DAGS_FOLDER).joinpath(folder_name)
    key_path = Path(DAGS_FOLDER).joinpath(f"{folder_name}.key")
    try:
        if folder_path.exists():
            return JSONResponse({"error": f"Folder {folder_name} already exists"}, status_code=400)

        key_content = await ssh_key.read()
        key_path.write_bytes(key_content)
        key_path.chmod(0o600)

        git_env = {"GIT_SSH_COMMAND": f"ssh -i {key_path} -o StrictHostKeyChecking=no"}
        Repo.clone_from(repo_url, folder_path, env=git_env)

        return JSONResponse({"success": f"Repository {folder_name} cloned successfully"})
    except GitCommandError as exc:
        if folder_path.exists():
            import shutil

            shutil.rmtree(folder_path)
        if key_path.exists():
            key_path.unlink()
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        if folder_path.exists():
            import shutil

            shutil.rmtree(folder_path)
        if key_path.exists():
            key_path.unlink()
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/repos/add-github", response_class=JSONResponse)
async def add_repo_github(repo_full_name: str = Form(...), folder_name: str = Form(...)):
    """Add a repository using GitHub App authentication"""
    folder_path = None
    github_marker = None
    try:
        folder_path = Path(DAGS_FOLDER).joinpath(folder_name)
        github_marker = Path(DAGS_FOLDER).joinpath(f"{folder_name}.github")

        # Check if folder already exists
        if folder_path.exists():
            return JSONResponse({"error": f"Folder {folder_name} already exists"}, status_code=400)

        # Get GitHub App token and build ASKPASS env for the clone
        token = _get_github_app_token()
        askpass = _create_github_askpass(token, folder_name)
        clone_env = {
            "GIT_ASKPASS": askpass,
            "GIT_USERNAME": "x-access-token",
            "GIT_TERMINAL_PROMPT": "0",
        }

        clone_url = f"https://github.com/{repo_full_name}.git"
        Repo.clone_from(clone_url, folder_path, env=clone_env)

        # Create marker file so _git_env knows to use GitHub App auth for this repo
        github_marker.touch()

        return JSONResponse({"success": f"Repository {folder_name} cloned successfully"})

    except Exception as exc:
        # Clean up on failure
        if folder_path and folder_path.exists():
            import shutil

            shutil.rmtree(folder_path)
        if github_marker and github_marker.exists():
            github_marker.unlink()
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/cleanup-branches/{folder:path}", response_class=JSONResponse)
async def cleanup_branches(folder: str):
    """Remove all local branches except the currently active one"""
    try:
        repo_path = Path(DAGS_FOLDER).joinpath(folder)
        repo = Repo(repo_path)

        if not repo.head.is_detached:
            active_branch = repo.active_branch.name
            branches_deleted = []
            errors = []

            for branch in repo.branches:
                if branch.name != active_branch:
                    try:
                        repo.delete_head(branch, force=True)
                        branches_deleted.append(branch.name)
                    except GitCommandError as exc:
                        errors.append(f"Failed to delete {branch.name}: {str(exc)}")

            return {
                "success": True,
                "active_branch": active_branch,
                "deleted_branches": branches_deleted,
                "errors": errors if errors else None,
            }
        else:
            return JSONResponse({"error": "Repository is in detached HEAD state"}, status_code=400)
    except InvalidGitRepositoryError:
        return JSONResponse({"error": "Not a valid git repository"}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


class AirflowMultiRepoDeploymentPlugin(AirflowPlugin):
    name = "multirepo_deploy_plugin"
    fastapi_apps = [{"app": app, "url_prefix": f"/{URL_PREFIX}", "name": "MultiRepo Deployment"}]
    react_apps = [
        {
            "name": "Deployments",
            "url_route": URL_PREFIX,
            "bundle_url": f"/{URL_PREFIX}/multirepo-deploy-ui/main.umd.cjs",
            "destination": "nav",
        }
    ]
