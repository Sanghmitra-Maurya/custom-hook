import json
import subprocess
import requests
import time
import re
import os
import sys
from hooks.setup_details import get_decrypted_tokens
from hooks.language_config import get_language_config, get_supported_languages, find_coverage_file
from .setup_details import decrypt_token
from .sonar_config import SonarConfig

class SonarQubeCheck:
    def __init__(self, host, project_key, encrypted_token, language="project-default", sonar_config=None):
        self.sonar_host = host
        self.project_key = project_key
        self.encrypted_token = encrypted_token
        self.language = language
        self.sonar_config = sonar_config or {}
        self.lang_config = get_language_config(language)
        self.issue_counts = {
            "blocker": 0,
            "critical": 0,
            "major": 0,
            "minor": 0,
            "info": 0
        }
        self.hospots_count = 0

    def _get_auth_token(self):
        """Decrypt token only when needed for API calls."""
        env_token = os.getenv("SONAR_TOKEN")
        print("===environment variable token",env_token)
        if env_token:
            return env_token.strip()
        return decrypt_token(self.encrypted_token)

    def _get_coverage_property_key(self):
        """Determine coverage property key from sonar config."""
        # Check for specific coverage properties in sonar config
        for key in self.sonar_config.keys():
            if 'coverage' in key.lower() and 'reportpaths' in key.lower():
                return key
        return None

    def _get_coverage_path(self):
        """Get coverage path from sonar config."""
        for key, value in self.sonar_config.items():
            if 'coverage' in key.lower() and 'reportpaths' in key.lower() and value:
                return value
        return ''

    def _add_default_config(self, cmd):
        """Add default hook configuration to command."""
        sources = self.sonar_config.get('sources', '.')
        exclusions = self.sonar_config.get('exclusions', '')
        tests = self.sonar_config.get('tests', '')
        test_inclusions = self.sonar_config.get('test_inclusions', '')
       
        cmd.extend([
            f"-Dsonar.sources={sources}",
            f"-Dsonar.exclusions={exclusions}" if exclusions else "-Dsonar.exclusions=",
        ])
       
        if tests:
            cmd.append(f"-Dsonar.tests={tests}")
        if test_inclusions:
            cmd.append(f"-Dsonar.test.inclusions={test_inclusions}")
       
        coverage_path = self._get_coverage_path()
        if not coverage_path or not os.path.exists(coverage_path):
        # Try to find coverage file if not specified or doesn't exist
            for lang in get_supported_languages():
                found_path = find_coverage_file(lang)
                if found_path:
                    coverage_path = found_path
                    break

        if coverage_path and os.path.exists(coverage_path):
            coverage_key = self._get_coverage_property_key()
            if coverage_key:
                cmd.append(f"-D{coverage_key}={coverage_path}")

    def _add_language_config(self, cmd):
        """Add language-specific configuration to command."""
        cmd.extend([
            "-Dsonar.sources=.",
            f"-Dsonar.exclusions={self.lang_config['exclusions']}",
            f"-Dsonar.inclusions={self.lang_config['inclusions']}",
            f"-Dsonar.test.inclusions={self.lang_config['test_paths']}"
        ])
       
        coverage_path = find_coverage_file(self.language)
        if coverage_path:
            coverage_map = {
                "python": f"-Dsonar.python.coverage.reportPaths={coverage_path}",
                "javascript": f"-Dsonar.javascript.lcov.reportPaths={coverage_path}",
                "typescript": f"-Dsonar.javascript.lcov.reportPaths={coverage_path}",
                "java": f"-Dsonar.coverage.jacoco.xmlReportPaths={coverage_path}"
            }
            if self.language in coverage_map:
                cmd.append(coverage_map[self.language])

    # 1. Run the analysis
    def run_analysis(self):
        print(f"Starting sonar-scanner analysis for {self.language}...")
        config_manager = SonarConfig()
        scanner_major = config_manager._get_scanner_version()
        token = self._get_auth_token()
        auth_arg = (
        f"-Dsonar.token={token}"
        if scanner_major >= 7
        else f"-Dsonar.login={token}"
        )
        print(f"Using SonarScanner version: {scanner_major}")
        try:
            cmd = [
                "sonar-scanner.bat",
                f"-Dsonar.projectKey={self.project_key}",
                f"-Dsonar.host.url={self.sonar_host}",
                auth_arg
            ]
           
            if self.language == "project-default":
                print("Using configuration from sonar properties file")
                self._add_default_config(cmd)
            else:
                self._add_language_config(cmd)

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print("Error running sonar-scanner:")
            print(e.stderr)
            raise

    # 2. Wait for analysis to finish (poll CE task API)
    def extract_ce_task_id(self, scanner_output):
        for line in scanner_output.splitlines():
            if "/api/ce/task?id=" in line:
                match = re.search(r'id=([a-f0-9\-]+)', line)
                if match:
                    return match.group(1)
        return None


    def wait_for_analysis(self, ce_task_id):
        url = f"{self.sonar_host}/api/ce/task?id={ce_task_id}"
        print(f"Waiting for CE Task ID: {ce_task_id} to complete...")

        while True:
            try:
                resp = requests.get(url, auth=(self._get_auth_token(), ""), timeout=30)
                if resp.status_code == 200:
                    task = resp.json().get('task', {})
                    status = task.get('status')
                    print(f"Current status: {status}")

                    if status in ["SUCCESS", "FAILED", "CANCELED"]:
                        print(f"CE Task completed with status: {status}")
                        return status
                else:
                    print(f"Failed to fetch task status. HTTP {resp.status_code}")
            except Exception as e:
                print(f"Error fetching task status: {e}")

            time.sleep(2)

    # Step 3: Get Issues
    def fetch_issues(self):
        issues_url = (
            f"{self.sonar_host}/api/issues/search?"
            f"componentKeys={self.project_key}"
            f"&resolved=false"
            f"&ps=100"
        )

        warn_list = []
        error_list = []
        error_msgs = []

        resp = requests.get(issues_url, auth=(self._get_auth_token(), ""), timeout=30)

        if resp.status_code == 200:
            issues = resp.json().get('issues', [])
            if not issues:
                print(f"\n{'='*40}  No Issues Found {'='*40}\n")
            else:
                for issue in issues:
                    severity = issue.get('severity')
                    severity_lower = severity.lower()  # Convert to lowercase for case-insensitive comp
                    message = issue.get('message')
                    component = issue.get('component', '').split(":")[-1]
                    line = issue.get('line', 'N/A')
                    rule = issue.get('rule', '').split(":")[-1]
                    msg = f"[{severity}] {component}:{line} — {message} ({rule})"

                    error_data = {
                    "file": component,
                    "line": int(line) if isinstance(line, int) or str(line).isdigit() else None,
                    "full_error": msg
                    }

                    if severity_lower in self.issue_counts:
                        self.issue_counts[severity_lower] += 1
                    else:
                        self.issue_counts[severity_lower] = 1

                    if severity in ["MINOR","INFO"]:
                        warn_list.append(msg)
                    else:
                        error_list.append(msg)
                        error_msgs.append(error_data)

            print(f"\n{'='*40}  {len(warn_list)} Warnings Found {'='*40}\n")
            for idx, warn in enumerate(warn_list, start=1):
                print(f"{idx}. {warn}\n")
            print(f"\n{'='*40} {len(error_list)} Errors Found {'='*40}\n")
            for idx, error in enumerate(error_list, start=1):
                print(f"{idx}. {error}\n")

        else:
            print("Failed to fetch issues.")
            print(resp.text)
       
        return error_msgs

    # Step 4: Get Security Hotspots
    def fetch_hotspots(self):
        hotspots_url = (
            f"{self.sonar_host}/api/hotspots/search?"
            f"projectKey={self.project_key}"
            f"&status=TO_REVIEW"  # or remove to get all statuses
            f"&ps=100"
        )

        hotspots_resp = requests.get(hotspots_url, auth=(self._get_auth_token(), ""), timeout=30)

        if hotspots_resp.status_code == 200:
            hotspots = hotspots_resp.json().get('hotspots', [])
            if not hotspots:
                print(f"\n{'='*40}  No security Hotspots Found {'='*40}\n")
            else:
                self.hospots_count = len(hotspots)
                print(f"\n{'='*40}  {len(hotspots)} Security Hotspots Found {'='*40}\n")
                for idx, hotspot in enumerate(hotspots, start=1):
                    severity = hotspot.get('vulnerabilityProbability', 'N/A')
                    message = hotspot.get('message', 'N/A')
                    component = hotspot.get('component', '').split(":")[-1]
                    line = hotspot.get('line', 'N/A')
                    print(f"{idx}. [{severity}] {component}:{line} — {message}\n")
               
        else:
            print("Failed to fetch security hotspots.")
            print(hotspots_resp.text)

    # 5. Fetch the Quality Gate Status
    def fetch_quality_gate_status(self):
        qg_url = f"{self.sonar_host}/api/qualitygates/project_status?projectKey={self.project_key}"
        resp = requests.get(qg_url, auth=(self._get_auth_token(), ""), timeout=30)

        if resp.status_code == 200:
            project_status = resp.json()['projectStatus']
            status = resp.json()['projectStatus']['status']
            print(f"\nQuality Gate Status: {status}")
            
            failed_conditions = []
            if status == "ERROR":
                 conditions = project_status.get('conditions', [])
                 if conditions:
                    for idx, condition in enumerate(conditions, start=1):
                        if condition.get('status') == "ERROR":
                            metric = condition.get('metricKey', 'N/A')
                            actual = condition.get('actualValue', 'N/A')
                            error_threshold = condition.get('errorThreshold', 'N/A')
                            comparator = condition.get('comparator', 'GT')
                            op = ">" if comparator == "GT" else "<" if comparator == "LT" else comparator

                            failed_conditions.append({
                                "metric": metric,
                                "actual": actual,
                                "threshold": error_threshold,
                                "comparator": op
                                })

            return status, failed_conditions
        else:
            print("\nFailed to fetch quality gate status.")
            return None, []
   
    # 6. Generate JSON report for UI
    def generate_json_report(self, qg_status,failed_conditions,configured_hooks):
        report_file = "sonar-result.json"
       
        # Only generate report if current language is in configured hooks
        if configured_hooks and self.language not in configured_hooks:
            print(f"\nSkipping report generation for {self.language} - not configured in .pre-commit-config.yaml")
            return
       
        # Load existing report if it exists
        existing_report = {"languages": {}}
        if os.path.exists(report_file):
            try:
                with open(report_file, "r") as f:
                    loaded_report = json.load(f)
                    # Ensure 'languages' key exists, recreate if corrupted
                    if "languages" not in loaded_report:
                        print(f"\nCorrupted {report_file} found (missing 'languages' key), creating new file")
                        existing_report = {"languages": {}}
                    else:
                        existing_report = loaded_report
            except (json.JSONDecodeError, KeyError) as e:
                print(f"\nError reading {report_file}: {e}, creating new file")
                existing_report = {"languages": {}}
       
        # Remove languages not in configured hooks
        if configured_hooks:
            existing_report["languages"] = {k: v for k, v in existing_report["languages"].items() if k in configured_hooks}
       
        # Add current language results
        existing_report["languages"][self.language] = {
            "status": "success" if qg_status == "OK" else "failed",
            "issues": self.issue_counts,
            "security_hotspots": self.hospots_count,
            "quality_gate_failures": failed_conditions if qg_status != "OK" else []
        }
       
        # Write updated report
        with open(report_file, "w") as f:
            json.dump(existing_report, f, indent=2)
       
        return existing_report

def main():
    tokens = get_decrypted_tokens()
    sonar_token = tokens["SONAR_TOKEN"]
    if not sonar_token:
        print("SONAR_TOKEN not found in environment.")
        exit(1)

    # Get language from command line args or default to "default"
    language = "project-default"  # project-default hook
    if len(sys.argv) > 1:
        specified_lang = sys.argv[1].lower()
        if specified_lang in get_supported_languages():
            language = specified_lang
        else:
            print(f"Unsupported language: {specified_lang}")
            print(f"Supported languages: {', '.join(get_supported_languages())}")
            exit(1)

    # Load configuration using SonarConfig
    config_manager = SonarConfig()
    config = config_manager.load_config(sonar_token)
   
    # Print config summary only for first language
    if not os.path.exists(".git/.sonar_config_printed"):
        config_manager.print_defaults_summary()
        with open(".git/.sonar_config_printed", "w") as f:
            f.write("printed")
   
    # Pass sonar_config for project-default hook, None for others
    sonar_config = config if language == "project-default" else None
    sonar = SonarQubeCheck(config['host'], config['project_key'], config['token'], language, sonar_config)

    try:
        output = sonar.run_analysis()
        ce_task_id = sonar.extract_ce_task_id(output)
        if not ce_task_id:
            print("Failed to extract ceTaskId.")
            exit(1)

        sonar.wait_for_analysis(ce_task_id)
        error_list = sonar.fetch_issues()
        sonar.fetch_hotspots()

        qg_status, failed_conditions = sonar.fetch_quality_gate_status()
        sonar.generate_json_report(qg_status,failed_conditions, config['configured_hooks'])

        with open(".git/.sonar_task_status", "w") as f:
            f.write(f"{ce_task_id}:{qg_status}")
       
        # Clear cache if this is the last hook to execute
        _clear_cache_if_last_hook(config_manager, config['configured_hooks'], language)
       
        if qg_status != "OK":
            exit(1)
    except Exception as e:
        print(f"Exception occurred: {e}")
        # Clear cache on error as well
        config_manager.clear_connection_cache()
        exit(1)

def _clear_cache_if_last_hook(config_manager, configured_hooks, current_language):
    """Clear connection cache if this is the last hook to execute."""
    if not configured_hooks:
        return
   
    # Check if current language is the last in the configured hooks list
    if current_language == configured_hooks[-1]:
        config_manager.clear_connection_cache()


if __name__ == "__main__":
    main()
