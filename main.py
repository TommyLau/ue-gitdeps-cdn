"""Main entry point for the application."""

import asyncio
import argparse
from pathlib import Path
from src.core.parser import GitDepsParser
from src.core.downloader import AsyncDownloader


def get_default_output_dir() -> Path:
    """Get the default output directory (./output)."""
    return Path(__file__).parent / "output"


async def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="Download UE dependencies from Commit.gitdeps.xml")
    parser.add_argument("xml_path", help="Path to Commit.gitdeps.xml")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent downloads")
    parser.add_argument("--output-dir", type=Path, default=get_default_output_dir(),
                      help="Directory for downloaded files (default: ./output)")
    parser.add_argument("--max-retries", type=int, default=5,
                      help="Maximum number of download retries (default: 5)")
    parser.add_argument("--timeout", type=int, default=30,
                      help="Download timeout in seconds (default: 30)")
    parser.add_argument("--chunk-size", type=int, default=8192,
                      help="Download chunk size in bytes (default: 8192)")
    parser.add_argument("--force-verify", action="store_true",
                      help="Force verification of all files even if previously verified")
    parser.add_argument("--show-stats", action="store_true",
                      help="Show verification statistics without downloading files")
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    deps_parser = GitDepsParser(args.xml_path)
    downloader = AsyncDownloader(
        max_workers=args.workers,
        max_retries=args.max_retries,
        timeout=args.timeout,
        chunk_size=args.chunk_size,
        output_dir=args.output_dir,
        force_verify=args.force_verify
    )
    
    # If only showing stats, display them and exit
    if args.show_stats and downloader.verification_manager:
        stats = downloader.verification_manager.get_statistics()
        print("\nVerification Statistics:")
        print(f"Total verified files: {stats['total_records']}")
        print(f"Valid files: {stats['status_counts'].get('VALID', 0)}")
        print(f"Files with hash mismatch: {stats['status_counts'].get('HASH_MISMATCH', 0)}")
        print(f"Corrupt files: {stats['status_counts'].get('CORRUPT', 0)}")
        print(f"Verifications today: {stats['recent_verifications']}")
        print(f"Verification database size: {stats['database_size_bytes'] / (1024*1024):.2f} MB")
        return 0
    
    try:
        # Parse dependencies
        deps = await deps_parser.parse()
        
        # Download files
        await downloader.download_batch(deps)
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code) 