"""
Script to analyze database usage over the past 2 weeks.
Shows daily averages and line plots for interactions, profiles, feedbacks, raw feedbacks, and requests.

Usage:
    python reflexio/scripts/analyze_db_usage.py --db-url "postgresql://user:pass@host:port/dbname"
"""

import argparse
import sys
from urllib.parse import urlparse

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import psycopg2
import psycopg2.extras


TABLES = ["interactions", "profiles", "feedbacks", "raw_feedbacks", "requests"]


def parse_db_url(url: str) -> dict:
    """
    Parse a PostgreSQL connection URL into psycopg2 connection parameters.

    Args:
        url (str): PostgreSQL URL (e.g., postgresql://user:pass@host:port/dbname)

    Returns:
        dict: Connection parameters for psycopg2.connect()
    """
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
    }


def query_daily_counts(cursor, table_name: str, days: int = 14) -> list[dict]:
    """
    Query daily row counts for a table over the specified number of days.

    Args:
        cursor: psycopg2 cursor
        table_name (str): Name of the table to query
        days (int): Number of days to look back (default: 14)

    Returns:
        list[dict]: List of dicts with 'day' (date) and 'count' (int) keys
    """
    if table_name not in TABLES:
        raise ValueError(f"Unknown table: {table_name}")
    query = """
        SELECT DATE(created_at) AS day, COUNT(*) AS count
        FROM {}
        WHERE created_at >= NOW() - INTERVAL '%s days'
        GROUP BY DATE(created_at)
        ORDER BY day;
    """.format(
        table_name
    )
    cursor.execute(query, [days])
    return [{"day": row["day"], "count": row["count"]} for row in cursor.fetchall()]


def print_summary(results: dict, days: int):
    """
    Print a summary table with daily averages for each metric.

    Args:
        results (dict): Mapping of table name to list of daily count dicts
        days (int): Number of days in the analysis window
    """
    print("\n" + "=" * 50)
    print(f"  Database Usage — Daily Averages (Past {days} Days)")
    print("=" * 50)
    print(f"  {'Table':<20} {'Daily Avg':>10}  {'Total':>8}")
    print("  " + "-" * 42)

    for table in TABLES:
        rows = results[table]
        total = sum(r["count"] for r in rows)
        num_days = days if days > 0 else 1
        avg = total / num_days
        print(f"  {table:<20} {avg:>10.1f}  {total:>8}")

    print("=" * 50 + "\n")


def plot_results(results: dict, days: int):
    """
    Generate a subplot figure with daily count line plots.

    Args:
        results (dict): Mapping of table name to list of daily count dicts
        days (int): Number of days in the analysis window
    """
    fig, axes = plt.subplots(3, 2, figsize=(12, 10))
    fig.suptitle(f"Database Usage — Past {days} Days", fontsize=14, fontweight="bold")

    for ax, table in zip(axes.flat, TABLES):
        rows = results[table]
        if rows:
            plot_days = [r["day"] for r in rows]
            counts = [r["count"] for r in rows]
        else:
            plot_days = []
            counts = []

        ax.plot(plot_days, counts, marker="o", linewidth=1.5, markersize=4)
        ax.set_title(table.replace("_", " ").title())
        ax.set_xlabel("Date")
        ax.set_ylabel("Count")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, alpha=0.3)

    # Hide unused subplot
    for ax in axes.flat[len(TABLES) :]:
        ax.set_visible(False)

    plt.tight_layout()
    output_file = "db_usage_report.png"
    plt.savefig(output_file, dpi=150)
    print(f"Plot saved to {output_file}")
    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze database usage over the past 2 weeks"
    )
    parser.add_argument(
        "--db-url",
        type=str,
        required=True,
        help='PostgreSQL connection URL (e.g., "postgresql://user:pass@host:port/dbname")',
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Number of days to analyze (default: 14)",
    )
    args = parser.parse_args()

    db_config = parse_db_url(args.db_url)
    try:
        conn = psycopg2.connect(**db_config)
    except psycopg2.OperationalError as e:
        print(f"Error: Could not connect to database: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        conn.set_client_encoding("UTF8")
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        results = {}
        for table in TABLES:
            results[table] = query_daily_counts(cursor, table, args.days)

        cursor.close()
    finally:
        conn.close()

    print_summary(results, args.days)
    plot_results(results, args.days)


if __name__ == "__main__":
    main()
