"""SonarQube configuration management module."""

import yaml
import os
from pathlib import Path
from typing import Dict, List, Tuple
from .sonar_cache import SonarConnectionCache


class SonarConfig:
    """Handles SonarQube configuration loading and validation."""
   
    # Configuration constants
    DEFAULT_HOST = "http://localhost:9000"
    DEFAULT_PROJECT_KEY = "code-enforser-demo"
    REQUIRED_KEYS = ["sonar.host.url", "sonar.projectKey"]
    TOKEN_KEYS = ["sonar.login", "sonar.token"]
   
    HOOK_LANGUAGE_MAP = {
        "check-sonar-quality-gate-ts": "typescript",
        "check-sonar-quality-gate-js": "javascript",
        "check-sonar-quality-gate-python": "python",
        "check-sonar-quality-gate-java": "java",
        "check-sonar-quality-gate": "project-default"
    }
   
    def __init__(self):
        self.defaults_used: List[str] = []
        self.cache = SonarConnectionCache()
   
    def load_config(self, env_token: str) -> Dict[str, str]:
        """Load and return complete SonarQube configuration."""
        # Check cache first
        cached_config = self.cache.get_connection()
        if cached_config:
            return cached_config
       
        properties_config = self._load_best_properties_file()
       
        config = {
            'host': self._get_with_default(properties_config, "sonar.host.url", self.DEFAULT_HOST),
            'project_key': self._get_with_default(properties_config, "sonar.projectKey", self.DEFAULT_PROJECT_KEY),
            'token': self._get_token(properties_config, env_token),
            'is_token': self._is_token_auth(properties_config, env_token),
            'configured_hooks': self._get_configured_hooks()
        }
       
        # Add additional properties for project-default hook
        if "project-default" in self._get_configured_hooks() or not self._get_configured_hooks():
            # Add all coverage-related properties
            coverage_props = {k: v for k, v in properties_config.items()
                            if 'coverage' in k.lower() and 'reportpaths' in k.lower()}
           
            config.update({
                'sources': properties_config.get('sonar.sources', ''),
                'exclusions': properties_config.get('sonar.exclusions', ''),
                'tests': properties_config.get('sonar.tests', ''),
                'test_inclusions': properties_config.get('sonar.test.inclusions', ''),
                **coverage_props  # Include all coverage properties
            })
       
        # Store in cache for subsequent hooks
        self.cache.store_connection(config)
       
        return config
   
    def _load_best_properties_file(self) -> Dict[str, str]:
        """Find and load the best available properties configuration."""
        properties_files = self._find_properties_files()
       
        if not properties_files:
            self._print_no_files_found()
            return {}
       
        self._print_found_files(properties_files)
        return self._find_first_complete_config(properties_files)
   
    def _print_no_files_found(self) -> None:
        """Print message when no configuration files are found."""
        print("No SonarQube configuration files found")
   
    def _print_found_files(self, files: List[str]) -> None:
        """Print list of found configuration files."""
        print(f"Found {len(files)} SonarQube configuration file(s):")
        for file in files:
            print(f"   {file}")
   
    def _find_first_complete_config(self, files: List[str]) -> Dict[str, str]:
        """Find first complete configuration, stopping when found."""
        print("\nChecking configuration completeness:")
        
        # Get environment token for completeness check
        from .setup_details import get_decrypted_tokens
        tokens = get_decrypted_tokens()
        env_token = tokens.get("SONAR_TOKEN", "")
       
        for config_file in files:
            config = self._parse_properties_file(config_file)
            if config:
                is_complete, missing_items = self._check_config_completeness(config, env_token)
                self._print_file_status(config_file, is_complete, missing_items)
               
                if is_complete:
                    print(f"\nUsing complete configuration: {config_file}")
                    return config
       
        # No complete config found, use last partial config
        if files:
            print("\nNo complete configuration found, using partial configuration with defaults")
            return self._parse_properties_file(files[-1])
       
        return {}
   
    def _print_file_status(self, file: str, is_complete: bool, missing_items: List[str]) -> None:
        """Print the completeness status of a configuration file."""
        if is_complete:
            print(f"   Complete: {file}")
        else:
            print(f"   Incomplete: {file} (missing: {', '.join(missing_items)})")
   

   
    def _find_properties_files(self) -> List[str]:
        """Find sonar properties files in current directory tree and parent directories."""
        # Search current directory tree first
        files = [str(p) for p in Path(".").rglob("sonar*.properties")]
       
        # Search parent directories if nothing found
        if not files:
            files = self._search_parent_directories()
       
        return files
   
    def _search_parent_directories(self) -> List[str]:
        """Search parent directories for sonar properties files."""
        current = Path(".").resolve()
        max_levels = 10
       
        for _ in range(max_levels):
            files = [str(p) for p in current.glob("sonar*.properties")]
            if files or current.parent == current:  # Found files or reached root
                return files
            current = current.parent
       
        return []
   
    def _parse_properties_file(self, filename: str) -> Dict[str, str]:
        """Parse a properties file into a dictionary."""
        config = {}
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if self._is_valid_property_line(line):
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
        except (FileNotFoundError, IOError, UnicodeDecodeError):
            pass  # Return empty config on any file reading error
       
        return config
   
    def _is_valid_property_line(self, line: str) -> bool:
        """Check if a line is a valid property line."""
        return line and not line.startswith("#") and "=" in line
   
    def _check_config_completeness(self, config: Dict[str, str], env_token: str = "") -> Tuple[bool, List[str]]:
        """Check configuration completeness and return missing items."""
        missing = self._get_missing_required_keys(config)
        missing.extend(self._get_missing_auth_keys(config, env_token))
       
        return len(missing) == 0, missing
   
    def _get_missing_required_keys(self, config: Dict[str, str]) -> List[str]:
        """Get list of missing required configuration keys."""
        return [key for key in self.REQUIRED_KEYS if key not in config]
   
    def _get_missing_auth_keys(self, config: Dict[str, str], env_token: str = "") -> List[str]:
        """Get list of missing authentication keys."""
        # Check if environment token is available
        if env_token:
            return []
        
        # Check if any token key exists in config
        if not any(key in config for key in self.TOKEN_KEYS):
            return ["authentication (sonar.login or sonar.token)"]
        return []
   
    def _get_with_default(self, config: Dict[str, str], key: str, default: str) -> str:
        """Get config value with default fallback and tracking."""
        if key not in config:
            self.defaults_used.append(f"{key} -> {default}")
        return config.get(key, default)
   
    def _is_token_auth(self, config: Dict[str, str], env_token: str) -> bool:
        """Determine if using token-based authentication vs login."""
        # Environment token is always token auth
        if env_token:
            return True
       
        # Check if sonar.token is used in config (vs sonar.login)
        return "sonar.token" in config
   
    def _get_token(self, config: Dict[str, str], env_token: str) -> bytes:
        """Get SonarQube token from environment or config, return encrypted."""
        from .setup_details import encrypt_token
       
        # Environment token takes precedence
        if env_token:
            self.defaults_used.append(f"Using token from environment: {env_token[:8]}...")
            return encrypt_token(env_token)
       
        # Fall back to config file token
        if "sonar.token" in config:
            token_val = config["sonar.token"]
            self.defaults_used.append(f"Using sonar.token from properties file: {token_val[:8]}...")
            return encrypt_token(token_val)
        
        if "sonar.login" in config:
            login_val = config["sonar.login"]
            self.defaults_used.append(f"Using sonar.login from properties file: {login_val[:8]}...")
            return encrypt_token(login_val)
       
        # No token found
        self.defaults_used.append("No token found")
        return encrypt_token("")
   
    def _get_configured_hooks(self) -> List[str]:
        """Parse .pre-commit-config.yaml to get configured sonar hooks."""
        try:
            config = self._load_precommit_config()
            return self._extract_sonar_hooks(config)
        except (FileNotFoundError, yaml.YAMLError):
            return []
   
    def _load_precommit_config(self) -> Dict:
        """Load and parse .pre-commit-config.yaml file."""
        with open(".pre-commit-config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
   
    def _extract_sonar_hooks(self, config: Dict) -> List[str]:
        """Extract sonar hook languages from pre-commit config."""
        hooks = []
        for repo in config.get("repos", []):
            for hook in repo.get("hooks", []):
                hook_id = hook.get("id", "")
                if hook_id in self.HOOK_LANGUAGE_MAP:
                    hooks.append(self.HOOK_LANGUAGE_MAP[hook_id])
        return hooks
   
    def clear_connection_cache(self) -> None:
        """Clear the connection cache."""
        self.cache.clear_cache()
   
    def print_defaults_summary(self) -> None:
        """Print summary of default values used."""
        if not self.defaults_used:
            return
       
        print("\nDefaults applied:")
        for default in self.defaults_used:
            print(f"   {default}")
        print()