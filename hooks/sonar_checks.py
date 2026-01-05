import subprocess
import requests
import time
import re
import os
import json
from hooks.setup_details import decrypt_token
from hooks.language_config import (
    get_language_config,
    get_supported_languages,
    find_coverage_file,
)


class SonarQubeCheck:
    def __init__(self, host, project_key, auth, language="project-default", sonar_config=None):
        self.host = host
        self.project_key = project_key
        self.auth = auth
        self.language = language
        self.sonar_config = sonar_config or {}
        self.lang_config = get_language_config(language)

    # ---------------- ANALYSIS ----------------

    def run_analysis(self):
        print(f"Running SonarScanner for {self.language}")

        token = decrypt_token(self.auth.token)
        print(f"Token source: {self.auth.source}")
        cmd = [
            "sonar-scanner.bat",
            f"-Dsonar.projectKey={self.project_key}",
            f"-Dsonar.host.url={self.host}",
        ]

        # IMPORTANT:
        # Scanner 7+ → uses env token ONLY
        # Scanner <=6 → allow sonar.login
        if self.auth.source == "sonar.login":
            cmd.append(f"-Dsonar.login={token}")
        else:
            os.environ["SONAR_TOKEN"] = token

        if self.language == "project-default":
            self._add_default_config(cmd)
        else:
            self._add_language_config(cmd)

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError("SonarScanner failed")

        return result.stdout

    # ---------------- CONFIG HELPERS ----------------

    def _add_default_config(self, cmd):
        cmd.append(f"-Dsonar.sources={self.sonar_config.get('sources', '.')}")
        if self.sonar_config.get("exclusions"):
            cmd.append(f"-Dsonar.exclusions={self.sonar_config['exclusions']}")

        for k, v in self.sonar_config.items():
            if "coverage" in k.lower() and v and os.path.exists(v):
                cmd.append(f"-D{k}={v}")

    def _add_language_config(self, cmd):
        cmd.extend([
            "-Dsonar.sources=.",
            f"-Dsonar.exclusions={self.lang_config['exclusions']}",
            f"-Dsonar.inclusions={self.lang_config['inclusions']}",
            f"-Dsonar.test.inclusions={self.lang_config['test_paths']}",
        ])

        coverage = find_coverage_file(self.language)
        if coverage:
            mapping = {
                "python": "sonar.python.coverage.reportPaths",
                "javascript": "sonar.javascript.lcov.reportPaths",
                "typescript": "sonar.javascript.lcov.reportPaths",
                "java": "sonar.coverage.jacoco.xmlReportPaths",
            }
            if self.language in mapping:
                cmd.append(f"-D{mapping[self.language]}={coverage}")

    # ---------------- POST ANALYSIS ----------------

    def extract_ce_task_id(self, output):
        for line in output.splitlines():
            if "/api/ce/task?id=" in line:
                m = re.search(r"id=([a-f0-9\-]+)", line)
                if m:
                    return m.group(1)
        return None

    def wait_for_analysis(self, task_id):
        url = f"{self.host}/api/ce/task?id={task_id}"
        token = decrypt_token(self.auth.token)

        while True:
            r = requests.get(url, auth=(token, ""), timeout=30)
            if r.status_code == 200:
                status = r.json()["task"]["status"]
                print("Status:", status)
                if status in ("SUCCESS", "FAILED", "CANCELED"):
                    return status
            time.sleep(2)
