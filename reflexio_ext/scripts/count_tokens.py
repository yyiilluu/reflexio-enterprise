#!/usr/bin/env python3
"""
Token counter script for analyzing token usage in files.

This script counts tokens in text files using tiktoken (OpenAI's tokenizer).
Supports single files or entire directories.

Usage:
    python count_tokens.py <file_or_directory> [--model MODEL] [--extensions EXTS]

Examples:
    # Count tokens in a single file
    python count_tokens.py /path/to/file.py

    # Count tokens in a directory (Python files only by default)
    python count_tokens.py /path/to/directory

    # Count tokens with specific model encoding
    python count_tokens.py /path/to/file.py --model gpt-4

    # Count tokens in multiple file types
    python count_tokens.py /path/to/directory --extensions .py,.md,.txt

Requirements:
    pip install tiktoken
"""

import argparse
import sys
from pathlib import Path


def count_tokens_in_text(text: str, model: str = "gpt-4") -> int:
    """
    Count tokens in a text string using tiktoken.

    Args:
        text (str): The text to count tokens for
        model (str): The model encoding to use (default: gpt-4)

    Returns:
        int: Number of tokens
    """
    try:
        import tiktoken
    except ImportError:
        print("Error: tiktoken is not installed.")
        print("Install it with: pip install tiktoken")
        sys.exit(1)

    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print(f"Warning: Model '{model}' not found, using cl100k_base encoding (GPT-4)")
        encoding = tiktoken.get_encoding("cl100k_base")

    tokens = encoding.encode(text)
    return len(tokens)


def count_tokens_in_file(file_path: Path, model: str = "gpt-4") -> dict[str, any]:
    """
    Count tokens in a single file.

    Args:
        file_path (Path): Path to the file
        model (str): The model encoding to use

    Returns:
        dict: Dictionary with file info and token count
    """
    try:
        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        token_count = count_tokens_in_text(content, model)

        return {
            "path": str(file_path),
            "tokens": token_count,
            "chars": len(content),
            "lines": content.count("\n") + 1,
            "error": None,
        }
    except UnicodeDecodeError:
        return {
            "path": str(file_path),
            "tokens": 0,
            "chars": 0,
            "lines": 0,
            "error": "Unable to decode file (binary or non-UTF-8)",
        }
    except Exception as e:
        return {
            "path": str(file_path),
            "tokens": 0,
            "chars": 0,
            "lines": 0,
            "error": str(e),
        }


def count_tokens_in_directory(
    directory: Path, extensions: list[str], model: str = "gpt-4"
) -> list[dict[str, any]]:
    """
    Count tokens in all files in a directory with specified extensions.

    Args:
        directory (Path): Path to the directory
        extensions (List[str]): List of file extensions to include (e.g., ['.py', '.md'])
        model (str): The model encoding to use

    Returns:
        list: List of dictionaries with file info and token counts
    """
    results = []

    for ext in extensions:
        # Find all files with this extension
        pattern = f"**/*{ext}"
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                result = count_tokens_in_file(file_path, model)
                results.append(result)

    return results


def format_number(num: int) -> str:
    """Format number with commas for readability."""
    return f"{num:,}"


def print_results(results: list[dict[str, any]], show_details: bool = True):
    """
    Print token counting results in a formatted table.

    Args:
        results (list): List of result dictionaries
        show_details (bool): Whether to show per-file details
    """
    # Filter out errors
    valid_results = [r for r in results if r["error"] is None]
    error_results = [r for r in results if r["error"] is not None]

    if not valid_results and not error_results:
        print("No files found.")
        return

    # Calculate totals
    total_tokens = sum(r["tokens"] for r in valid_results)
    total_chars = sum(r["chars"] for r in valid_results)
    total_lines = sum(r["lines"] for r in valid_results)
    total_files = len(valid_results)

    # Print summary
    print("\n" + "=" * 80)
    print("TOKEN COUNTING SUMMARY")
    print("=" * 80)
    print(f"Total Files:  {format_number(total_files)}")
    print(f"Total Tokens: {format_number(total_tokens)}")
    print(f"Total Chars:  {format_number(total_chars)}")
    print(f"Total Lines:  {format_number(total_lines)}")
    print("=" * 80)

    # Print per-file details if requested
    if show_details and len(valid_results) > 1:
        print("\nPER-FILE BREAKDOWN:")
        print("-" * 80)
        print(f"{'File':<50} {'Tokens':>12} {'Lines':>8}")
        print("-" * 80)

        # Sort by token count (descending)
        sorted_results = sorted(valid_results, key=lambda x: x["tokens"], reverse=True)

        for result in sorted_results:
            # Get relative path for better readability
            path = Path(result["path"])
            display_path = str(path.name) if len(str(path)) > 47 else str(path)
            if len(display_path) > 47:
                display_path = "..." + display_path[-44:]

            print(
                f"{display_path:<50} {format_number(result['tokens']):>12} {format_number(result['lines']):>8}"
            )

        print("-" * 80)

    # Print errors if any
    if error_results:
        print("\nERRORS:")
        print("-" * 80)
        for result in error_results:
            print(f"❌ {result['path']}")
            print(f"   Error: {result['error']}")
        print("-" * 80)

    print()


def main():
    """Main function to parse arguments and run token counting."""
    parser = argparse.ArgumentParser(
        description="Count tokens in files using tiktoken (OpenAI tokenizer)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Count tokens in a single file
  python count_tokens.py /path/to/file.py

  # Count tokens in a directory (Python files only by default)
  python count_tokens.py /path/to/directory

  # Count tokens with specific model encoding
  python count_tokens.py /path/to/file.py --model gpt-4o

  # Count tokens in multiple file types
  python count_tokens.py /path/to/directory --extensions .py,.md,.txt

  # Hide per-file details (show only summary)
  python count_tokens.py /path/to/directory --no-details
        """,
    )

    parser.add_argument("path", type=str, help="Path to file or directory to analyze")

    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4",
        help="Model encoding to use (default: gpt-4). Options: gpt-4, gpt-3.5-turbo, text-davinci-003, etc.",
    )

    parser.add_argument(
        "--extensions",
        type=str,
        default=".py",
        help="Comma-separated list of file extensions to include (default: .py). Example: .py,.md,.txt",
    )

    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Hide per-file details, show only summary",
    )

    args = parser.parse_args()

    # Parse path
    target_path = Path(args.path)

    if not target_path.exists():
        print(f"Error: Path '{args.path}' does not exist.")
        sys.exit(1)

    # Parse extensions
    extensions = [ext.strip() for ext in args.extensions.split(",")]
    # Ensure extensions start with a dot
    extensions = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]

    print(f"\n🔍 Analyzing: {target_path}")
    print(f"📊 Model: {args.model}")

    # Count tokens
    if target_path.is_file():
        print("📄 Type: Single file\n")
        result = count_tokens_in_file(target_path, args.model)
        print_results([result], show_details=False)
    elif target_path.is_dir():
        print("📁 Type: Directory")
        print(f"🔍 Extensions: {', '.join(extensions)}\n")
        results = count_tokens_in_directory(target_path, extensions, args.model)
        print_results(results, show_details=not args.no_details)
    else:
        print(f"Error: '{args.path}' is neither a file nor a directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
