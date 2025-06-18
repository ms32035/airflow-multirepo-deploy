import importlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from git import GitCommandError, Repo
from git.exc import InvalidGitRepositoryError

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin


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
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
post_hook = get_post_hook()

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def list_repos(request: Request):
    repos = []
    for f in Path(dags_folder).iterdir():
        if f.is_dir() and f.name != ".git":
            repo = _load_repo(f, f.name)
            if repo:
                repos.append(repo)
    return templates.TemplateResponse("repos.html", {"request": request, "repos": repos, "title": "Repos"})


@app.get("/status/{folder:path}", response_class=HTMLResponse)
async def repo_status(request: Request, folder: str):
    repo_meta = _load_repo(Path(dags_folder).joinpath(folder), folder)
    if not repo_meta:
        return RedirectResponse("")
    allowed_branches = conf.get("multirepo_deploy", "allowed_branches", fallback=None)
    if allowed_branches:
        branch_choices = [brn for brn in repo_meta.remote_branches if brn in allowed_branches.split(",")]
    else:
        branch_choices = repo_meta.remote_branches
    selected_branch = f"origin/{repo_meta.active_branch}"
    return templates.TemplateResponse(
        "deploy.html",
        {
            "request": request,
            "repo": repo_meta,
            "form": {"branches": branch_choices, "selected": selected_branch},
            "title": f"Status: {folder}",
        },
    )


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
    except GitCommandError:
        pass
    if post_hook:
        try:
            post_hook(Path(dags_folder).joinpath(folder))
        except Exception:
            pass
    return RedirectResponse("", status_code=303)


class AirflowMultiRepoDeploymentPlugin(AirflowPlugin):
    name = "multirepo_deploy_plugin"
    fastapi_apps = [{"app": app, "url_prefix": "/deployment", "name": "MultiRepo Deployment"}]
