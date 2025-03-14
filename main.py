"""Main entry point for the application."""

import asyncio
import argparse
from pathlib import Path
from src.core.parser import GitDepsParser
from src.core.downloader import AsyncDownloader
from src.core.cache import CacheManager


def get_default_cache_dir() -> Path:
    """Get the default cache directory (./output)."""
    return Path(__file__).parent / "output"


async def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="Download UE dependencies from Commit.gitdeps.xml")
    parser.add_argument("xml_path", help="Path to Commit.gitdeps.xml")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent downloads")
    parser.add_argument("--cache-dir", type=Path, default=get_default_cache_dir(),
                      help="Directory for cached files (default: ./output)")
    parser.add_argument("--max-retries", type=int, default=3,
                      help="Maximum number of download retries (default: 3)")
    parser.add_argument("--timeout", type=int, default=30,
                      help="Download timeout in seconds (default: 30)")
    parser.add_argument("--chunk-size", type=int, default=8192,
                      help="Download chunk size in bytes (default: 8192)")
    parser.add_argument("--cache-max-size", type=str, default="100GB",
                      help="Maximum cache size (default: 100GB)")
    parser.add_argument("--cache-cleanup-threshold", type=int, default=90,
                      help="Cache cleanup threshold percentage (default: 90)")
    
    args = parser.parse_args()
    
    # Create cache directory if it doesn't exist
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    deps_parser = GitDepsParser(args.xml_path)
    downloader = AsyncDownloader(
        max_workers=args.workers,
        max_retries=args.max_retries,
        timeout=args.timeout,
        chunk_size=args.chunk_size,
        cache_dir=args.cache_dir
    )
    cache_manager = CacheManager(
        cache_dir=args.cache_dir,
        max_size=args.cache_max_size,
        cleanup_threshold=args.cache_cleanup_threshold
    )
    
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