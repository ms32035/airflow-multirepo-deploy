import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "ui_build"

    def initialize(self, version, build_data):
        ui_dir = Path(self.root) / "src" / "airflow_multirepo_deploy" / "ui"
        subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=ui_dir, check=True)
        subprocess.run(["pnpm", "build"], cwd=ui_dir, check=True)
