import sys

from .cli import main

if __name__ == "__main__":
    # No arguments (e.g. double-clicked) -> open the GUI
    main(sys.argv[1:] or ["gui"])
