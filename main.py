"""Main entry point for the application."""

import asyncio
import argparse
import signal
import sys
import os
from pathlib import Path
from src.core.parser import GitDepsParser
from src.core.downloader import AsyncDownloader


def get_default_output_dir() -> Path:
    """Get the default output directory (./output)."""
    return Path(__file__).parent / "output"


def get_system_proxies() -> dict:
    """Get system proxy settings from environment variables."""
    # Debug print of proxy environment variables
    print("Environment Variables:")
    print(f"  HTTP_PROXY:  {os.environ.get('HTTP_PROXY')}")
    print(f"  http_proxy:  {os.environ.get('http_proxy')}")
    print(f"  HTTPS_PROXY: {os.environ.get('HTTPS_PROXY')}")
    print(f"  https_proxy: {os.environ.get('https_proxy')}")
    print(f"  NO_PROXY:    {os.environ.get('NO_PROXY')}")
    print(f"  no_proxy:    {os.environ.get('no_proxy')}")
    
    return {
        'http': os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY'),
        'https': os.environ.get('https_proxy') or os.environ.get('HTTPS_PROXY'),
        'no_proxy': os.environ.get('no_proxy') or os.environ.get('NO_PROXY')
    }


async def main():
    """Main application entry point."""
    global _global_downloader
    
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
    
    # Get system proxy settings
    proxies = get_system_proxies()
    proxies = {k: v for k, v in proxies.items() if v is not None}
    print(f"Using proxies: {proxies}")
    
    # Initialize components
    deps_parser = GitDepsParser(args.xml_path)
    downloader = AsyncDownloader(
        max_workers=args.workers,
        max_retries=args.max_retries,
        timeout=args.timeout,
        chunk_size=args.chunk_size,
        output_dir=args.output_dir,
        force_verify=args.force_verify,
        proxies=proxies if proxies else None
    )
    
    # Set the global downloader reference for the exception handler
    _global_downloader = downloader
    
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
        # Ensure database is properly closed
        if downloader.verification_manager:
            downloader.verification_manager.close()
        return 0
    
    try:
        # Parse dependencies
        deps = await deps_parser.parse()
        
        # Download files
        await downloader.download_batch(deps)
        
    except KeyboardInterrupt:
        print("\nOperation interrupted by user. Flushing database...")
        # Ensure database is properly flushed on keyboard interrupt
        if downloader.verification_manager:
            downloader.verification_manager.flush()
        return 1
    except Exception as e:
        print(f"Error: {e}")
        # Ensure database is properly flushed on error
        if downloader.verification_manager:
            downloader.verification_manager.flush()
        return 1
    
    return 0


# Store a reference to the downloader for the global exception handler
_global_downloader = None

if __name__ == "__main__":
    # Define a custom exception handler for asyncio.run
    def custom_exception_handler(loop, context):
        msg = context.get("exception", context["message"])
        print(f"Caught exception: {msg}")
        # Use the global downloader reference
        if _global_downloader is not None and _global_downloader.verification_manager:
            _global_downloader.verification_manager.flush()
        sys.exit(1)
    
    try:
        # Configure the event loop policy to use our custom exception handler
        # This will be used by asyncio.run() internally
        policy = asyncio.get_event_loop_policy()
        loop = policy.new_event_loop()
        loop.set_exception_handler(custom_exception_handler)
        asyncio.set_event_loop(loop)
        
        # Run the main function
        exit_code = asyncio.run(main())
        exit(exit_code)
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
        exit(1) 