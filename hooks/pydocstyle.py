import sys
import subprocess

def main():
    # Your desired pydocstyle args
    args = ["--select=D100,D102,D103"]
    args += sys.argv[1:]

    # Use python -m pydocstyle to ensure it's found
    result = subprocess.run([sys.executable, "-m", "pydocstyle"] + args)

    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
  
