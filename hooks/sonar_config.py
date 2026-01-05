"""
SonarQube configuration management module.
Supports both SonarScanner <=6.x and 7+ safely.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, NamedTuple
from .sonar_cache import SonarConnectionCache


class SonarAuth(NamedTuple):
    token: bytes
    source: str  # env | sonar.token | sonar.login


class SonarConfig:
    DEFAULT_HOST = "http://localhost:9000"
    DEFAULT_PROJECT_KEY = "code-enforser-demo"

    REQUIRED_KEYS = ["sonar.host.url", "sonar.projectKey"]

    def __init__(self):
        self.defaults_used: List[str] = []
        self.cache = SonarConnectionCache()

    # ---------------- PUBLIC API ----------------

    def load_config(self, env_token: str) -> Dict:
        cached = self.cache.get_connection()
        if cached:
            return cached

        props = self._load_best_properties_file()

        auth = self._resolve_auth(props, env_token)

        config = {
            "host": self._get_with_default(props, "sonar.host.url", self.DEFAULT_HOST),
            "project_key": self._get_with_default(props, "sonar.projectKey", self.DEFAULT_PROJECT_KEY),
            "auth": auth,
            "configured_hooks": self._get_configured_hooks(),
        }

        # Extra config only for project-default hook
        if not config["configured_hooks"] or "project-default" in config["configured_hooks"]:
            config.update(self._extract_project_defaults(props))

        self.cache.store_connection(config)
        return config

    def clear_connection_cache(self):
        self.cache.clear_cache()

    def print_defaults_summary(self):
        if not self.defaults_used:
            return
        print("\nDefaults applied:")
        for d in self.defaults_used:
            print(f"   {d}")

    # ---------------- AUTH RESOLUTION ----------------

    def _resolve_auth(self, props: Dict[str, str], env_token: str) -> SonarAuth:
        """
        Priority:
        1. SONAR_TOKEN env (required for Scanner 7+)
        2. sonar.token (legacy)
        3. sonar.login (very old scanners)
        """
        from .setup_details import encrypt_token

        if env_token:
            return SonarAuth(encrypt_token(env_token), "env")

        if "sonar.token" in props:
            return SonarAuth(encrypt_token(props["sonar.token"]), "sonar.token")

        if "sonar.login" in props:
            return SonarAuth(encrypt_token(props["sonar.login"]), "sonar.login")

        raise RuntimeError("No Sonar authentication found (SONAR_TOKEN / sonar.token / sonar.login)")

    # ---------------- PROPERTIES FILE HANDLING ----------------

    def _load_best_properties_file(self) -> Dict[str, str]:
        files = self._find_properties_files()
        if not files:
            print("No SonarQube configuration files found")
            return {}

        for f in files:
            cfg = self._parse_properties_file(f)
            complete, _ = self._check_config_completeness(cfg)
            if complete:
                print(f"Using configuration: {f}")
                return cfg

        print("Using partial configuration with defaults")
        return self._parse_properties_file(files[-1])

    def _find_properties_files(self) -> List[str]:
        files = [str(p) for p in Path(".").rglob("sonar*.properties")]
        if files:
            return files

        cur = Path(".").resolve()
        for _ in range(10):
            files = [str(p) for p in cur.glob("sonar*.properties")]
            if files:
                return files
            if cur.parent == cur:
                break
            cur = cur.parent
        return []

    def _parse_properties_file(self, filename: str) -> Dict[str, str]:
        config = {}
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        config[k.strip()] = v.strip()
        except Exception:
            pass
        return config

    def _check_config_completeness(self, cfg: Dict[str, str]) -> Tuple[bool, List[str]]:
        missing = [k for k in self.REQUIRED_KEYS if k not in cfg]
        return len(missing) == 0, missing

    # ---------------- HELPERS ----------------

    def _get_with_default(self, cfg: Dict, key: str, default: str) -> str:
        if key not in cfg:
            self.defaults_used.append(f"{key} -> {default}")
        return cfg.get(key, default)

    def _extract_project_defaults(self, cfg: Dict) -> Dict:
        result = {
            "sources": cfg.get("sonar.sources", "."),
            "exclusions": cfg.get("sonar.exclusions", ""),
            "tests": cfg.get("sonar.tests", ""),
            "test_inclusions": cfg.get("sonar.test.inclusions", ""),
        }
        for k, v in cfg.items():
            if "coverage" in k.lower() and "reportpaths" in k.lower():
                result[k] = v
        return result

    def _get_configured_hooks(self) -> List[str]:
        try:
            with open(".pre-commit-config.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            return []

        hooks = []
        for repo in data.get("repos", []):
            for h in repo.get("hooks", []):
                hooks.append(h.get("id"))
        return hooks
