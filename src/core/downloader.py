"""Download manager for handling concurrent file downloads."""

import asyncio
from typing import List, Dict
import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm
from pathlib import Path
from src.core.cache import CacheManager


class AsyncDownloader:
    """Manage concurrent downloads with progress tracking."""
    
    def __init__(self, max_workers: int = 5, max_retries: int = 5,
                 timeout: int = 30, chunk_size: int = 8192, cache_dir: str | Path = None):
        """Initialize the downloader with configuration parameters."""
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.session = None
        self.cache_manager = CacheManager(cache_dir) if cache_dir else None
    
    async def __aenter__(self):
        """Create aiohttp session when entering context."""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session when exiting context."""
        if self.session:
            await self.session.close()
    
    async def download_file(self, url: str, dest: str | Path, file_size: int, expected_hash: str = None) -> bool:
        """Download a single file with progress tracking and retries."""
        if not self.session:
            raise RuntimeError("Downloader must be used as async context manager")
        
        if self.cache_dir:
            dest_path = self.cache_dir / dest
        else:
            dest_path = Path(dest)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
       
        for attempt in range(self.max_retries):
            try:
                # Check if file exists and verify size/hash
                status = "⬇️ NEW"  # Default: new download
                start_pos = 0

                if dest_path.exists():
                    current_size = dest_path.stat().st_size
                    
                    # If file is larger than expected, re-download
                    if current_size > file_size:
                        status = "📥 REDOWN"  # File too large, needs re-download
                        dest_path.unlink()
                    # If file size matches, verify hash
                    elif current_size == file_size and expected_hash and self.cache_manager:
                        actual_hash = self.cache_manager.calculate_hash(dest_path)
                        if actual_hash == "invalid_gzip_file":
                            status = "🔄 CORRUPT"  # File exists but can't be unzipped
                            dest_path.unlink()
                        elif actual_hash.lower() == expected_hash.lower():
                            return True  # File is valid
                        else:
                            status = "♻️ HASH"  # File exists but hash mismatch
                            dest_path.unlink()
                    # If file is smaller, try to resume download
                    elif current_size < file_size:
                        status = "⏯️ RESUME"  # Partial file, will resume
                        start_pos = current_size

                desc = f"[{status:^10}] {dest_path}"
                pbar = tqdm(total=file_size, initial=start_pos, unit='B', unit_scale=True, desc=desc, leave=False)

                headers = {'Range': f'bytes={start_pos}-'} if start_pos > 0 else {}
                async with self.session.get(url, headers=headers) as response:
                    if start_pos > 0 and response.status != 206:  # Resume failed
                        status = "📥 REDOWN"  # Switch to full re-download
                        start_pos = 0
                        pbar.reset()
                        continue
                    
                    if response.status not in (200, 206):
                        if attempt == self.max_retries - 1:
                            pbar.close()
                            return False
                        continue
                    
                    mode = 'ab' if start_pos > 0 else 'wb'
                    with open(dest_path, mode) as f:
                        async for chunk in response.content.iter_chunked(self.chunk_size):
                            f.write(chunk)
                            pbar.update(len(chunk))
                    
                    pbar.close()
                    
                    # Only verify hash if file size matches expected size
                    if dest_path.stat().st_size == file_size and expected_hash and self.cache_manager:
                        actual_hash = self.cache_manager.calculate_hash(dest_path)
                        if actual_hash == "invalid_gzip_file":
                            if dest_path.exists():
                                dest_path.unlink()
                            return False
                        hash_matches = actual_hash.lower() == expected_hash.lower()
                        if not hash_matches:
                            if attempt < self.max_retries - 1:  # Try one re-download on hash mismatch
                                status = "📥 REDOWN"
                                start_pos = 0
                                dest_path.unlink()
                                pbar.reset()
                                continue
                            if dest_path.exists():
                                dest_path.unlink()
                            return False
                    
                    return True
                    
            except Exception as e:
                if attempt == self.max_retries - 1:
                    pbar.set_description(f"❌ Error: {str(e)[:50]}...")
                    pbar.close()
                    return False
                
                # Get current file size for resume
                if dest_path.exists():
                    start_pos = dest_path.stat().st_size
                    status = "⏯️ RESUME"
                
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                pbar.reset(start_pos)  # Reset with new start position
                continue
        
        pbar.close()
        return False
    
    async def download_batch(self, items: List[Dict]) -> None:
        """Handle concurrent downloads of multiple files."""
        async with self:
            # Create semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(self.max_workers)
            
            async def download_with_semaphore(item: Dict) -> bool:
                async with semaphore:
                    return await self.download_file(
                        item['url'],
                        item['dest'],
                        item['compressed_size'],  # Pass compressed size for progress bar
                        item['hash']  # Use 'hash' key and get() to handle missing hash gracefully
                    )
            
            # Create tasks for all downloads
            tasks = [
                asyncio.create_task(download_with_semaphore(item))
                for item in items
            ]
            
            # Show overall progress
            total_files = len(tasks)
            with tqdm(total=total_files, desc=f"Total Progress ({total_files} files)") as pbar:
                completed = 0
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    completed += 1
                    pbar.update(1)
                    if result:
                        pbar.set_postfix({"success": f"{completed}/{total_files}"})
            
            # Print summary
            successful = sum(1 for task in tasks if task.result())
            print(f"\nDownload complete: {successful}/{total_files} files downloaded successfully") 