import os

def main():
    hook_path = os.path.join(".git", "hooks", "prepare-commit-msg")

    # The bash script content
    hook_content = """#!/bin/bash

msg_file="$1"
status_file=".git/.sonar_task_status"

if [[ -f "$status_file" ]]; then
    task_status=$(cat "$status_file")

    first_line=$(head -n1 "$msg_file")
    rest=$(tail -n +2 "$msg_file")

    echo "${first_line} ${task_status}" > "$msg_file"
    echo "$rest" >> "$msg_file"

    rm -f "$status_file"
fi
"""

    try:
        with open(hook_path, "w") as f:
            f.write(hook_content)

        # Make the file executable
        os.chmod(hook_path, 0o755)
        print("prepare-commit-msg hook installed successfully.")
    except Exception as e:
        print(f"Failed to install hook: {e}")

if __name__ == "__main__":
    main()