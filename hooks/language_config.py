"""Language configuration for SonarQube analysis."""
import os
import glob

LANGUAGE_CONFIGS = {
    "python": {
        "inclusions": "**/*.py",
        "exclusions": "venv/**,__pycache__/**,*.pyc,build/**,dist/**",
        "coverage_paths": "coverage.xml",
        "test_paths": "**/test_*.py,**/*_test.py,**/tests/**"
    },
    "javascript": {
        "inclusions": "**/*.js,**/*.jsx",
        "exclusions": "node_modules/**,build/**,dist/**,coverage/**,*.min.js",
        "coverage_paths": "coverage/lcov.info",
        "test_paths": "**/*.test.js,**/*.spec.js,**/tests/**,**/__tests__/**"
    },
    "typescript": {
        "inclusions": "**/*.ts,**/*.tsx",
        "exclusions": "node_modules/**,build/**,dist/**,coverage/**,*.d.ts",
        "coverage_paths": "coverage/lcov.info",
        "test_paths": "**/*.test.ts,**/*.spec.ts,**/tests/**,**/__tests__/**"
    },
    "java": {
        "inclusions": "**/*.java",
        "exclusions": "target/**,build/**,*.class",
        "coverage_paths": "target/site/jacoco/jacoco.xml",
        "test_paths": "**/test/**,**/*Test.java,**/*Tests.java"
    }
}

def get_language_config(language):
    """Get configuration for specified language."""
    return LANGUAGE_CONFIGS.get(language.lower(), LANGUAGE_CONFIGS["python"])

def get_supported_languages():
    """Get list of supported languages."""
    return list(LANGUAGE_CONFIGS.keys())

def find_coverage_file(language, base_path="."):
    """Find coverage file anywhere in the project."""
    config = LANGUAGE_CONFIGS.get(language.lower(), LANGUAGE_CONFIGS["python"])
    coverage_filename = os.path.basename(config['coverage_paths'])

    # Search recursively for the coverage file
    for root, dirs, files in os.walk(base_path):
        # Skip common directories
        dirs[:] = [d for d in dirs if d not in ['node_modules', 'venv', '__pycache__', '.git']]
        if coverage_filename in files:
            return os.path.join(root, coverage_filename)

   
