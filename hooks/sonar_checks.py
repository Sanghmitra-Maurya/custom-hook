import json
import subprocess
import requests
import time
import re
import os
from hooks.get_suggestions import get_code_suggestion_from_error
from hooks.setup_details import get_decrypted_tokens

class SonarQubeCheck:
    def __init__(self, host, project_key, token):
        self.sonar_host = host
        self.project_key = project_key
        self.sonar_token = token
        self.issue_counts = {
            "blocker": 0,
            "critical": 0,
            "major": 0,
            "minor": 0,
            "info": 0
        }
        self.hospots_count = 0


    # 1. Run the analysis
    def run_analysis(self):
        print("Starting sonar-scanner analysis...")
        try:
            result = subprocess.run(
                ["sonar-scanner.bat",
                f"-Dsonar.projectKey={self.project_key}",
                "-Dsonar.sources=.",
                f"-Dsonar.host.url={self.sonar_host}",
                f"-Dsonar.login={self.sonar_token}",
                "-Dsonar.exclusions=venv/**",
                # "-Dsonar.inclusions=**/*.py",
                "-Dsonar.python.coverage.reportPaths=coverage.xml"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            print("Analysis triggered.")

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
                resp = requests.get(url, auth=(self.sonar_token, ""))
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

        resp = requests.get(issues_url, auth=(self.sonar_token, ""))

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

        hotspots_resp = requests.get(hotspots_url, auth=(self.sonar_token, ""))

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
        resp = requests.get(qg_url, auth=(self.sonar_token, ""))

        if resp.status_code == 200:
            status = resp.json()['projectStatus']['status']
            print(f"\nQuality Gate Status: {status}")
            return status
        else:
            print("\nFailed to fetch quality gate status.")
            return 
    
    # 6. Generate JSON report for UI
    def generate_json_report(self, qg_status):
        report = {
        "status": "success" if qg_status == "OK" else "failed",
        "issues": self.issue_counts,
        "security_hotspots": self.hospots_count
        }
        with open("sonar-result.json", "w") as f:
            json.dump(report, f, indent=2)
    
    def get_code_context(self, file_path, line_num, context_lines=3):
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
                start = max(0, line_num - context_lines - 1)
                end = min(len(lines), line_num + context_lines)

                # Highlight the target line with a comment
                context_snippet = ""
                for i in range(start, end):
                    line = lines[i].rstrip("\n")
                    if i == line_num - 1:
                        context_snippet += f">>> {line}   # <-- Issue reported here\n"
                    else:
                        context_snippet += f"    {line}\n"
                return context_snippet

        except Exception as e:
            print(f"[Error reading file: {e}]")
            return None

    def give_code_suggestions(self, error_items):
        print(f"\n{'='*40} AI Suggestions {'='*40}\n")
        for idx, item in enumerate(error_items, start=1):
            file_path = item['file']
            line_num = item['line']
            if line_num is None:
                print(f"Skipping sugestion for file: {file_path} - Line info missing")
                continue

            context_code = self.get_code_context(file_path, line_num)
            if context_code is None:
                print(f"Skipping suggestion for file: {file_path} - Unable to fetch code context")
                continue

            prompt = (
                f"Issue: {item['full_error']}\n"
                f"Code context from {file_path} around line {line_num}:\n"
                f"{context_code}\n"
                "- Please suggest a fix for this issue:\n"
                "- Focus only on the line on which issue us occured (denoted by # <-- Issue reported here), avoid giving suggestions for other lines unless mandatory.\n"
                "- Provide one complete and precise solution.\n"
                "- Always check syntax, type mismatch, etc before providing final solution.\n"
                "- Try to answer in one paragraph only, strictly keep only 3 sections, ##Cause, ##Resolution/Changes needed, ##Sample Code.\n"
                "- Clearly mention what should be removed, changed, or added.\n"
                "- Avoid generic advice; tailor your suggestion to the actual context.\n"
                "- Assume the code is part of a production pipeline — avoid insecure practices like hardcoding credentials.\n"
            )
            
            suggestion = get_code_suggestion_from_error(prompt)
            print(f"{idx}. {item['full_error']}\n")
            print(f"Code Snippet:\n{context_code}")
            print(f"AI Suggestion:\n{suggestion}\n")


def main():
    tokens = get_decrypted_tokens()
    sonar_token = tokens["SONAR_TOKEN"]
    if not sonar_token:
        print("SONAR_TOKEN not found in environment.")
        exit(1)

    sonar = SonarQubeCheck("http://localhost:9000", "VS_code_extension", sonar_token)

    try:
        output = sonar.run_analysis()
        ce_task_id = sonar.extract_ce_task_id(output)
        if not ce_task_id:
            print("Failed to extract ceTaskId.")
            exit(1)

        sonar.wait_for_analysis(ce_task_id)
        error_list = sonar.fetch_issues()
        sonar.fetch_hotspots()

        qg_status = sonar.fetch_quality_gate_status()
        sonar.generate_json_report(qg_status)

        with open(".git/.sonar_task_status", "w") as f:
            f.write(f"{ce_task_id}:{qg_status}")
        if qg_status != "OK":
            sonar.give_code_suggestions(error_list)
            exit(1)
    except Exception as e:
        print(f"Exception occurred: {e}")
        exit(1)


if __name__ == "__main__":
    main()