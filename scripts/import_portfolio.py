"""Import a portfolio CSV into local storage."""

from __future__ import annotations

import argparse
from decimal import Decimal

from twadvisor.portfolio.manager import PortfolioManager


def main() -> None:
    """Run the portfolio import script."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--cash", default="0")
    args = parser.parse_args()

    manager = PortfolioManager()
    manager.import_csv(args.file, cash=Decimal(args.cash))


if __name__ == "__main__":
    main()
