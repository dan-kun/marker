"""Entry point for Marker application."""

import sys
from .application import MarkerApplication


def main():
    app = MarkerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
