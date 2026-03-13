"""
Script to test Supabase connection and database access.

This script verifies that:
1. Connection to Supabase can be established
2. Database tables are accessible
3. Basic operations (select, count) work correctly

Usage:
    # Test with required command-line arguments
    python -m reflexio.scripts.test_supabase_connection \
        --url https://your-project.supabase.co \
        --key your-supabase-key

    # Test specific tables
    python -m reflexio.scripts.test_supabase_connection \
        --url https://your-project.supabase.co \
        --key your-supabase-key \
        --tables profiles,interactions

Required arguments:
    --url: Supabase project URL
    --key: Supabase API key
"""

import argparse
import logging
import sys

from supabase import Client, create_client

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default tables to test
DEFAULT_TABLES = [
    "profiles",
    "interactions",
    "requests",
    "feedbacks",
    "raw_feedbacks",
    "profile_change_logs",
    "agent_success_evaluation_result",
    "_operation_state",
]


def test_connection(supabase_url: str, supabase_key: str) -> Client | None:
    """
    Test Supabase connection.

    Args:
        supabase_url (str): Supabase project URL
        supabase_key (str): Supabase API key

    Returns:
        Optional[Client]: Supabase client if successful, None otherwise
    """
    try:
        logger.info("Testing Supabase connection...")
        logger.info(f"  URL: {supabase_url}")
        logger.info(f"  Key: {supabase_key[:10]}...")

        client = create_client(supabase_url, supabase_key)
        logger.info("✓ Successfully created Supabase client")
        return client

    except Exception as e:
        logger.error(f"✗ Failed to create Supabase client: {e}")
        return None


def test_table_access(client: Client, table_name: str) -> dict:
    """
    Test access to a specific table.

    Args:
        client (Client): Supabase client
        table_name (str): Name of the table to test

    Returns:
        dict: Test results with status and details
    """
    result = {"table": table_name, "accessible": False, "count": None, "error": None}

    try:
        logger.info(f"Testing table '{table_name}'...")

        # Try to count records (doesn't require data to exist)
        response = (
            client.table(table_name).select("*", count="exact").limit(0).execute()
        )

        result["accessible"] = True
        result["count"] = response.count if response.count is not None else 0

        logger.info(f"  ✓ Table '{table_name}' is accessible")
        logger.info(f"    Record count: {result['count']}")

        # Try to fetch a sample record (if any exist)
        if result["count"] > 0:
            sample_response = client.table(table_name).select("*").limit(1).execute()
            if sample_response.data:
                logger.info("    ✓ Successfully fetched sample record")
                # Show column names
                columns = list(sample_response.data[0].keys())
                logger.info(f"    Columns: {', '.join(columns)}")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"  ✗ Failed to access table '{table_name}': {e}")

    return result


def test_database_functions(client: Client) -> dict:
    """
    Test custom database functions (RPC calls).

    Args:
        client (Client): Supabase client

    Returns:
        dict: Test results for each function
    """
    results = {}

    # Test functions used by the application
    functions_to_test = [
        "match_profiles",
        "match_interactions",
        "match_feedbacks",
        "match_raw_feedbacks",
    ]

    logger.info("Testing database functions...")

    for func_name in functions_to_test:
        try:
            # Try calling with minimal parameters (will likely fail but confirms function exists)
            # We use a dummy embedding to test if the function is callable
            dummy_embedding = [0.0] * 512  # Reduced embedding dimensions

            _response = client.rpc(
                func_name,
                {
                    "query_embedding": dummy_embedding,
                    "match_threshold": 0.9,
                    "match_count": 1,
                },
            ).execute()

            results[func_name] = {"exists": True, "callable": True, "error": None}
            logger.info(f"  ✓ Function '{func_name}' is callable")

        except Exception as e:  # noqa: PERF203
            error_msg = str(e)
            # Function might exist but fail for other reasons (e.g., no data)
            if (
                "function" in error_msg.lower()
                and "does not exist" in error_msg.lower()
            ):
                results[func_name] = {
                    "exists": False,
                    "callable": False,
                    "error": error_msg,
                }
                logger.error(f"  ✗ Function '{func_name}' does not exist")
            else:
                results[func_name] = {
                    "exists": True,
                    "callable": True,
                    "error": error_msg,
                }
                logger.info(
                    f"  ✓ Function '{func_name}' exists (call failed as expected: {error_msg[:50]}...)"
                )

    return results


def run_tests(supabase_url: str, supabase_key: str, tables: list[str]) -> bool:
    """
    Run all connection and access tests.

    Args:
        supabase_url (str): Supabase project URL
        supabase_key (str): Supabase API key
        tables (list[str]): List of table names to test

    Returns:
        bool: True if all tests passed, False otherwise
    """
    logger.info("=" * 60)
    logger.info("Supabase Connection Test")
    logger.info("=" * 60)
    logger.info("")

    # Test connection
    client = test_connection(supabase_url, supabase_key)
    if not client:
        logger.error("Connection test failed!")
        return False

    logger.info("")
    logger.info("=" * 60)
    logger.info("Testing Table Access")
    logger.info("=" * 60)
    logger.info("")

    # Test table access
    table_results = []
    for table_name in tables:
        result = test_table_access(client, table_name)
        table_results.append(result)
        logger.info("")

    # Test database functions
    logger.info("=" * 60)
    logger.info("Testing Database Functions")
    logger.info("=" * 60)
    logger.info("")

    function_results = test_database_functions(client)
    logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    accessible_tables = [r for r in table_results if r["accessible"]]
    inaccessible_tables = [r for r in table_results if not r["accessible"]]

    logger.info(f"Tables tested: {len(tables)}")
    logger.info(f"  ✓ Accessible: {len(accessible_tables)}")
    logger.info(f"  ✗ Inaccessible: {len(inaccessible_tables)}")

    if inaccessible_tables:
        logger.warning("Inaccessible tables:")
        for result in inaccessible_tables:
            logger.warning(f"  - {result['table']}: {result['error']}")

    # Show record counts
    logger.info("")
    logger.info("Record counts:")
    for result in accessible_tables:
        logger.info(f"  {result['table']}: {result['count']} records")

    # Function summary
    logger.info("")
    logger.info("Database functions:")
    callable_functions = [
        name for name, res in function_results.items() if res["callable"]
    ]
    missing_functions = [
        name for name, res in function_results.items() if not res["exists"]
    ]

    logger.info(f"  ✓ Callable: {len(callable_functions)}")
    if missing_functions:
        logger.warning(f"  ✗ Missing: {len(missing_functions)}")
        for func_name in missing_functions:
            logger.warning(f"    - {func_name}")

    logger.info("")
    logger.info("=" * 60)

    # Overall result
    all_passed = len(inaccessible_tables) == 0 and len(missing_functions) == 0

    if all_passed:
        logger.info("✓ All tests passed!")
        return True
    logger.warning("⚠ Some tests failed - see details above")
    return False


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test Supabase connection and database access",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with required arguments
  python -m reflexio.scripts.test_supabase_connection \\
    --url https://your-project.supabase.co \\
    --key your-key

  # Test specific tables only
  python -m reflexio.scripts.test_supabase_connection \\
    --url https://your-project.supabase.co \\
    --key your-key \\
    --tables profiles,interactions,requests
        """,
    )
    parser.add_argument(
        "--url", type=str, required=True, help="Supabase project URL (required)"
    )
    parser.add_argument(
        "--key", type=str, required=True, help="Supabase API key (required)"
    )
    parser.add_argument(
        "--tables",
        type=str,
        help="Comma-separated list of tables to test (default: all standard tables)",
    )
    args = parser.parse_args()

    # Get tables to test
    if args.tables:
        tables = [t.strip() for t in args.tables.split(",")]
    else:
        tables = DEFAULT_TABLES

    # Run tests
    success = run_tests(args.url, args.key, tables)

    sys.exit(0 if success else 1)
