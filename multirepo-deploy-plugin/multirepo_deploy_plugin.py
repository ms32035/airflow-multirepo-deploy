import importlib
import mimetypes
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from git import GitCommandError, Repo
from git.exc import InvalidGitRepositoryError
from starlette.staticfiles import StaticFiles

mimetypes.add_type("application/javascript", ".cjs")


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


def _git_env(dags_folder, folder: str) -> dict:
    git_identity_file = Path(dags_folder).joinpath(f"{folder}.key")
    return {"GIT_SSH_COMMAND": f"ssh -i {git_identity_file}"} if Path(git_identity_file).exists() else {}


def _load_repo(path, folder) -> RepoMeta | bool:
    try:
        return RepoMeta.from_repo(Repo(path), folder)
    except InvalidGitRepositoryError:
        return False


dags_folder = conf.get("core", "dags_folder")
REACT_APP_DIR = conf.get("multirepo_deploy", "react_app_dir", fallback=Path(__file__).parent / "ui" / "dist")
URL_PREFIX = conf.get("multirepo_deploy", "url_prefix", fallback="deployment")
post_hook = get_post_hook()

app = FastAPI()
app.mount(
    "/multirepo-deploy-ui",
    StaticFiles(directory=REACT_APP_DIR, html=True),
    name="multirepo-deploy-ui",
)


@app.get("/api/repos", response_class=JSONResponse)
async def list_repos_api():
    repos = []
    for f in Path(dags_folder).iterdir():
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
    return {"repos": repos}


@app.get("/api/status/{folder:path}", response_class=JSONResponse)
async def repo_status_api(folder: str):
    repo_meta = _load_repo(Path(dags_folder).joinpath(folder), folder)
    if not repo_meta:
        return JSONResponse({"error": "Repository not found"}, status_code=404)

    git_env = _git_env(dags_folder, folder)
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
    repo = Repo(path=Path(dags_folder).joinpath(folder))
    new_branch = branches
    new_local_branch = "/".join(new_branch.split("/")[1:])
    git_env = _git_env(dags_folder, folder)

    try:
        repo.git.checkout(new_local_branch, env=git_env)
        repo.remotes.origin.fetch(env=git_env)
        repo.git.reset("--hard", f"origin/{new_local_branch}", env=git_env)
        if post_hook:
            post_hook(Path(dags_folder).joinpath(folder))
    except (GitCommandError, Exception) as exc:
        error_message = traceback.format_exception(exc)

        return JSONResponse({"error": error_message}, status_code=400)

    return JSONResponse({"success": "Deployment successful"})


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
