import importlib
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from airflow.www.decorators import action_logging
from airflow.www import auth
from airflow.security import permissions


from flask import render_template, flash, redirect, request
from flask_appbuilder import BaseView, expose
from flask_wtf import FlaskForm
from git import Repo
from git.exc import InvalidGitRepositoryError
from git.cmd import GitCommandError
from wtforms.fields import SelectField


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
            remote_branches = [
                ref.name for ref in repo.remotes.origin.refs if "HEAD" not in ref.name
            ]
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
            datetime.fromtimestamp(self.committed_date).strftime("%Y-%m-%d %H:%M:%S")
            if self.committed_date
            else None
        )


def get_post_hook():
    callable_name = conf.get("multirepo_deploy", "post_hook", fallback=None)
    if not callable_name:
        return None
    module_name, callable_name = callable_name.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, callable_name)


class DeploymentView(BaseView):
    dags_folder = conf.get("core", "dags_folder")

    template_folder = Path(__file__).resolve().parent.joinpath("templates")
    route_base = "/deployment"
    post_hook = get_post_hook()

    def render(self, template, **context):
        return render_template(
            template,
            base_template=self.appbuilder.base_template,
            appbuilder=self.appbuilder,
            **context,
        )

    @staticmethod
    def _load_repo(path, folder) -> RepoMeta | bool:
        try:
            return RepoMeta.from_repo(Repo(path), folder)

        except InvalidGitRepositoryError:
            return False

    @expose("/repos")
    @auth.has_access(((permissions.ACTION_CAN_READ, permissions.RESOURCE_VARIABLE),))
    @action_logging
    def list(self):
        repos = list()

        for f in Path(self.dags_folder).iterdir():
            if f.is_dir() and f.name != ".git":
                if repo := self._load_repo(f, f.name):
                    repos.append(repo)

        return self.render_template("repos.html", repos=repos)

    @expose("/status/<path:folder>")
    @auth.has_access(((permissions.ACTION_CAN_READ, permissions.RESOURCE_CONNECTION),))
    @action_logging
    def status(self, folder):
        repo_meta = self._load_repo(Path(self.dags_folder).joinpath(folder), folder)

        if not repo_meta:
            flash(f"Folder {folder} is not a git repository", "error")
            return redirect("/deployment/repos")

        for rem in repo_meta.repo.remotes:
            try:
                rem.fetch(prune=True, env=self._git_env(folder))
            except GitCommandError as gexc:
                flash(str(gexc), "error")

        allowed_branches = conf.get(
            "multirepo_deploy", "allowed_branches", fallback=None
        )
        branch_choices = (
            [
                (brn, brn)
                for brn in repo_meta.remote_branches
                if brn in allowed_branches.split(",")
            ]
            if allowed_branches
            else [(brn, brn) for brn in repo_meta.remote_branches]
        )

        form = GitBranchForm()
        form.branches.choices = branch_choices
        form.branches.data = f"origin/{repo_meta.active_branch}"

        return self.render_template("deploy.html", repo=repo_meta, form=form)

    @expose("/deploy/<path:folder>", methods=["POST"])
    @auth.has_access(((permissions.ACTION_CAN_EDIT, permissions.RESOURCE_CONNECTION),))
    @action_logging
    def deploy(self, folder):
        repo = Repo(path=Path(self.dags_folder).joinpath(folder))

        new_branch = request.form.get("branches")
        new_local_branch = "/".join(new_branch.split("/")[1:])

        git_env = self._git_env(folder)

        try:
            repo.git.checkout(new_local_branch, env=git_env)
            repo.remotes.origin.fetch(env=git_env)
            result = repo.git.reset("--hard", f"origin/{new_local_branch}", env=git_env)
            if new_local_branch == repo.active_branch.name:
                flash(f"Successfully updated branch: {new_local_branch}\n{result}")
            else:
                flash(f"Successfully changed to branch: {new_local_branch}\n{result}")
        except GitCommandError as gexc:
            flash(str(gexc), "error")

        if DeploymentView.post_hook:
            try:
                res = DeploymentView.post_hook(Path(self.dags_folder).joinpath(folder))
                flash(f"Successfully ran post hook: {res}")
            except Exception as e:
                flash(f"Failed to run post hook: {e}", "error")

        return redirect("/deployment/repos")

    def _git_env(self, folder: str) -> dict:
        git_identity_file = Path(self.dags_folder).joinpath(f"{folder}.key")

        return (
            {"GIT_SSH_COMMAND": f"ssh -i {git_identity_file}"}
            if Path(git_identity_file).exists()
            else {}
        )


deployment_view = DeploymentView()
appbuilder_package = {
    "name": "Deployment",
    "category": "Admin",
    "view": deployment_view,
}


class AirflowMultiRepoDeploymentPlugin(AirflowPlugin):
    name = "multirepo_deploy_plugin"
    appbuilder_views = [appbuilder_package]


class GitBranchForm(FlaskForm):
    branches = SelectField("Git branch")
