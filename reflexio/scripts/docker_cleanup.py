#!/usr/bin/env python3
"""
Script to clean up unused Docker resources.

This script removes:
- Stopped containers
- Unused images (dangling and optionally all unused)
- Unused volumes
- Unused networks
- Build cache

Usage:
    python docker_cleanup.py              # Basic cleanup (dangling resources only)
    python docker_cleanup.py --all        # Aggressive cleanup (all unused resources)
    python docker_cleanup.py --dry-run    # Show what would be removed without removing
"""

import argparse
import subprocess


def run_command(command: list[str], dry_run: bool = False) -> tuple[bool, str]:
    """
    Run a docker command and return success status and output.

    Args:
        command: Command to run as list of strings
        dry_run: If True, only print the command without executing

    Returns:
        tuple: (success: bool, output: str)
    """
    cmd_str = " ".join(command)
    if dry_run:
        print(f"  [DRY RUN] Would run: {cmd_str}")
        return True, ""

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)  # noqa: S603
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except FileNotFoundError:
        return False, "Docker command not found. Is Docker installed?"


def clean_containers(dry_run: bool = False) -> None:
    """Remove all stopped containers."""
    print("\n🗑️  Cleaning stopped containers...")
    success, output = run_command(["docker", "container", "prune", "-f"], dry_run)
    if success and output:
        print(f"  {output.strip()}")
    elif not success:
        print(f"  Error: {output}")


def clean_images(all_unused: bool = False, dry_run: bool = False) -> None:
    """
    Remove unused images.

    Args:
        all_unused: If True, remove all unused images, not just dangling ones
        dry_run: If True, only show what would be removed
    """
    print("\n🖼️  Cleaning unused images...")
    cmd = ["docker", "image", "prune", "-f"]
    if all_unused:
        cmd.append("-a")
    success, output = run_command(cmd, dry_run)
    if success and output:
        print(f"  {output.strip()}")
    elif not success:
        print(f"  Error: {output}")


def clean_volumes(dry_run: bool = False) -> None:
    """Remove all unused volumes."""
    print("\n💾 Cleaning unused volumes...")
    success, output = run_command(["docker", "volume", "prune", "-f"], dry_run)
    if success and output:
        print(f"  {output.strip()}")
    elif not success:
        print(f"  Error: {output}")


def clean_networks(dry_run: bool = False) -> None:
    """Remove all unused networks."""
    print("\n🌐 Cleaning unused networks...")
    success, output = run_command(["docker", "network", "prune", "-f"], dry_run)
    if success and output:
        print(f"  {output.strip()}")
    elif not success:
        print(f"  Error: {output}")


def clean_build_cache(dry_run: bool = False) -> None:
    """Remove build cache."""
    print("\n🏗️  Cleaning build cache...")
    success, output = run_command(["docker", "builder", "prune", "-f"], dry_run)
    if success and output:
        print(f"  {output.strip()}")
    elif not success:
        print(f"  Error: {output}")


def show_disk_usage() -> None:
    """Show current Docker disk usage."""
    print("\n📊 Current Docker disk usage:")
    success, output = run_command(["docker", "system", "df"])
    if success:
        print(output)
    else:
        print(f"  Error: {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Clean up unused Docker resources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python docker_cleanup.py              # Basic cleanup
  python docker_cleanup.py --all        # Remove all unused resources
  python docker_cleanup.py --dry-run    # Preview what would be removed
  python docker_cleanup.py --all --dry-run  # Preview aggressive cleanup
        """,
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Remove all unused resources (not just dangling)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be removed without actually removing",
    )
    parser.add_argument(
        "--skip-volumes",
        action="store_true",
        help="Skip cleaning volumes (volumes may contain important data)",
    )

    args = parser.parse_args()

    print("🐳 Docker Cleanup Script")
    print("=" * 40)

    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made")

    # Show current usage
    show_disk_usage()

    # Run cleanup
    clean_containers(args.dry_run)
    clean_images(all_unused=args.all, dry_run=args.dry_run)

    if not args.skip_volumes:
        clean_volumes(args.dry_run)
    else:
        print("\n💾 Skipping volume cleanup (--skip-volumes)")

    clean_networks(args.dry_run)
    clean_build_cache(args.dry_run)

    # Show final usage
    if not args.dry_run:
        print("\n" + "=" * 40)
        print("✅ Cleanup complete!")
        show_disk_usage()
    else:
        print("\n" + "=" * 40)
        print("ℹ️  Dry run complete. Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
