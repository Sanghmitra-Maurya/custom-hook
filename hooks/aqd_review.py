import keyboard
import time

def main():
    time.sleep(3)

    # Press Alt + Win + Q
    keyboard.press_and_release('alt+windows+q')

    time.sleep(5)

    text = """Conduct a comprehensive full project code review analyzing all security vulnerabilities, code quality issues, best practices violations, infrastructure security, dependency risks, and performance concerns across the entire codebase.
    Show all issues in Code issues panel."""
    
    # Write the entire text as one prompt (replace newlines with spaces)
    keyboard.write(text.replace('\n', ' ').replace('\r', ' '))
    keyboard.press_and_release('enter')


if __name__ == "__main__":
    main()