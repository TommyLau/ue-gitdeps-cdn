"""Download manager for handling concurrent file downloads."""

import asyncio
from typing import List, Dict
import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm
from pathlib import Path


class AsyncDownloader:
    """Manage concurrent downloads with progress tracking."""
    
    def __init__(self, max_workers: int = 5, max_retries: int = 3,
                 timeout: int = 30, chunk_size: int = 8192, cache_dir: str | Path = None):
        """Initialize the downloader with configuration parameters."""
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.session = None
    
    async def __aenter__(self):
        """Create aiohttp session when entering context."""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session when exiting context."""
        if self.session:
            await self.session.close()
    
    async def download_file(self, url: str, dest: str | Path, file_size: int) -> bool:
        """Download a single file with progress tracking and retries."""
        if not self.session:
            raise RuntimeError("Downloader must be used as async context manager")
        
        if self.cache_dir:
            dest_path = self.cache_dir / dest
        else:
            dest_path = Path(dest)
            
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create progress bar for this file
        desc = f"Downloading {dest_path}"  # Show full path
        pbar = tqdm(total=file_size, unit='B', unit_scale=True, desc=desc, leave=False)
        
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url) as response:
                    if response.status != 200:
                        if attempt == self.max_retries - 1:
                            pbar.close()
                            return False
                        continue
                    
                    with open(dest_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(self.chunk_size):
                            f.write(chunk)
                            pbar.update(len(chunk))
                    
                    pbar.close()
                    return True
                    
            except Exception as e:
                if attempt == self.max_retries - 1:
                    print(f"\nError downloading {url}: {e}")
                    if dest_path.exists():
                        dest_path.unlink()
                    pbar.close()
                    return False
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                pbar.reset()
        
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
                        item['size']  # Pass file size for progress bar
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