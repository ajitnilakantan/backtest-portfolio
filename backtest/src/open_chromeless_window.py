"""Open Chrome Browser Window in App Mode

This module provides a utility function to launch a Chrome browser window in
app mode (minimal chrome) for displaying Jupyter/Marimo notebooks or web content.
It automatically detects the operating system and uses platform-specific commands.

This is primarily used by the Marimo application framework when launching notebook
servers that require a browser interface.

Functions
---------
main() : Launches a browser window with the specified URL in app mode.
"""

import subprocess
import sys


def main():
    """Opens a URL in a Chrome browser window in app mode, with platform-specific fallback logic.

    This function is designed to be called by Marimo when a notebook launches a browser
    URL. It automatically detects the operating system and launches the appropriate
    browser executable.

    Platform-specific behavior:

    - **Windows**:
      - Attempts to open the URL in Google Chrome using `chrome.exe`
      - Falls back to Microsoft Edge if Chrome is not installed
      - Uses `--app={url}` flag to launch Chrome in app mode (minimized to taskbar, no address bar)

    - **macOS**:
      - Opens the URL in Google Chrome directly (assumes Chrome is installed)
      - Uses `--app={url}` flag for app mode
      - Requires Chrome to be installed; no fallback mechanism

    - **Linux**:
      - Opens the URL in Google Chrome (assumes `google-chrome` command is available in PATH)
      - Uses `--app={url}` flag for app mode
      - Assumes Chrome is installed and accessible via command line

    Parameters:
        None

    Returns:
        None

    Side Effects:
        - Launches a browser window with the specified URL in app mode
        - No browser window is created if less than 2 arguments are provided
        - Silently fails if the browser executable is not found or accessible

    Raises:
        No exceptions are raised; errors are silently caught via subprocess exceptions.

    Notes:
        - The function uses subprocess.Popen to launch the browser asynchronously
        - Marimo appends the notebook URL as the final command line argument
        - Browser windows are launched in the background; no output capture is performed
    """
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
