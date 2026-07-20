import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        return

    # Marimo appends the notebook URL as the final command line argument
    url = sys.argv[-1]

    # Windows
    if sys.platform == "win32":
        try:
            # Tries Chrome first
            subprocess.Popen([r"C:\Program Files\Google\Chrome\Application\chrome.exe", f"--app={url}"])
        except FileNotFoundError:
            # Falls back to Edge if Chrome is missing
            subprocess.Popen([r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", f"--app={url}"])

    # macOS
    elif sys.platform == "darwin":
        subprocess.Popen(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", f"--app={url}"])

    # Linux (Ubuntu/Debian)
    else:
        subprocess.Popen(["google-chrome", f"--app={url}"])


if __name__ == "__main__":
    main()
