"""Standalone WB entry point, same JSON format as ozon_parser.py."""
import sys
from main import main
from parsers import ParserWildberries

if __name__ == "__main__":
    raise SystemExit(main(["collect", "wb"] + sys.argv[1:]))
