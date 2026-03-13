import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Remove OPENAI_API_KEY from environment if it exists
if "OPENAI_API_KEY" in os.environ:
    del os.environ["OPENAI_API_KEY"]

from reflexio.server import OPENAI_API_KEY


def check_for_api_keys() -> bool:
    return OPENAI_API_KEY != ""


def main() -> int:
    retval = 0

    if check_for_api_keys():
        print("API key found in server/__init__.py")
        retval = 1

    return retval


if __name__ == "__main__":
    raise SystemExit(main())
