"""Download manager for handling concurrent file downloads."""

import asyncio
import hashlib
import gzip
from typing import List, Dict, Callable, Tuple
import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm
from pathlib import Path
from enum import Enum, auto


class DownloadStatus(Enum):
    """Enumeration of possible download status codes."""
    NEW = auto()       # New download
    RESUME = auto()    # Resuming partial download
    REDOWN = auto()    # Re-downloading file
    UNZIP = auto()     # Decompressing file
    VERIFY = auto()    # Verifying file hash
    VALID = auto()     # File is valid
    CORRUPT = auto()   # Corrupted file
    HASH = auto()      # Hash mismatch
    ERROR = auto()     # Download error


class AsyncDownloader:
    """Manage concurrent downloads with progress tracking."""
    
    def __init__(self, max_workers: int = 5, max_retries: int = 5,
                 timeout: int = 30, chunk_size: int = 8192, output_dir: str | Path = None):
        """Initialize the downloader with configuration parameters."""
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.output_dir = Path(output_dir) if output_dir else None
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
    
    def calculate_hash(self, file_path: str | Path, progress_callback=None) -> str:
        """
        Calculate SHA-1 hash of a file after decompressing gzipped content.
        
        Args:
            file_path: Path to the gzipped file to hash
            progress_callback: Optional callback function to report progress (phase, progress)
                               phase: 'decompress' or 'hash', progress: 0.0 to 1.0
        
        Returns:
            SHA-1 hash as hexadecimal string or "invalid_gzip_file" if decompression fails
        """
        sha1_hash = hashlib.sha1()
        file_path = Path(file_path)
        file_size = file_path.stat().st_size
        
        try:
            # Process gzip file - stream directly without storing in memory
            try:
                with gzip.open(file_path, 'rb') as gz_file:
                    # For progress reporting
                    total_read = 0
                    last_progress_report = 0
                    
                    # Read in chunks and update hash directly
                    while True:
                        chunk = gz_file.read(65536)  # Use larger chunks (64KB)
                        if not chunk:
                            break
                        
                        # Update hash with this chunk
                        sha1_hash.update(chunk)
                        
                        # Update decompression progress
                        if progress_callback:
                            total_read += len(chunk)
                            # Only report progress every ~1% to reduce overhead
                            current_progress = min(total_read / (file_size * 10), 1.0)  # Estimate decompressed size
                            if current_progress - last_progress_report >= 0.01:
                                progress_callback('decompress', current_progress)
                                last_progress_report = current_progress
                
                # Report 100% completion for decompression phase
                if progress_callback:
                    progress_callback('decompress', 1.0)
                    # Also report 100% for hash phase since we've already calculated it
                    progress_callback('hash', 1.0)
                
            except (OSError, EOFError, gzip.BadGzipFile) as e:
                print(f"  WARNING: Failed to decompress file for hash calculation: {e}")
                return "invalid_gzip_file"
        
        except Exception as e:
            print(f"  ERROR: Failed to calculate hash: {e}")
            return "invalid_gzip_file"
            
        return sha1_hash.hexdigest()
    
    def _get_status_indicator(self, status: DownloadStatus) -> str:
        """Get formatted status indicator with emoji.
        
        Args:
            status: DownloadStatus enum value
            
        Returns:
            Formatted status string with emoji
        """
        status_indicators = {
            DownloadStatus.NEW: "⬇️ NEW",         # New download
            DownloadStatus.RESUME: "⏯️ RESUME",   # Resuming partial download
            DownloadStatus.REDOWN: "📥 REDOWN",   # Re-downloading file
            DownloadStatus.UNZIP: "🔄 UNZIP",     # Decompressing file
            DownloadStatus.VERIFY: "🔍 VERIFY",   # Verifying file hash
            DownloadStatus.VALID: "✅ VALID",     # File is valid
            DownloadStatus.CORRUPT: "🔄 CORRUPT", # Corrupted file
            DownloadStatus.HASH: "♻️ HASH",       # Hash mismatch
            DownloadStatus.ERROR: "❌ ERROR"       # Download error
        }
        return status_indicators.get(status, f"❓ {status.name}")
    
    def _create_hash_progress_callback(self, pbar: tqdm, dest_path: Path, file_size: int) -> Callable:
        """Create a callback function for hash verification progress updates.
        
        Args:
            pbar: Progress bar to update
            dest_path: Path to the file being processed
            file_size: Expected file size
            
        Returns:
            Callback function for hash verification progress
        """
        def hash_progress_callback(phase, progress):
            if phase == 'decompress':
                status = self._get_status_indicator(DownloadStatus.UNZIP)
                pbar.set_description(f"[{status:^10}] {dest_path}")
                # Show full 0-100% for decompression
                pbar.n = int(file_size * progress)
                pbar.refresh()
            elif phase == 'hash':
                status = self._get_status_indicator(DownloadStatus.VERIFY)
                pbar.set_description(f"[{status:^10}] {dest_path}")
                # Show full 0-100% for hash verification
                pbar.n = int(file_size * progress)
                pbar.refresh()
        return hash_progress_callback
    
    def _update_progress_bar(self, pbar: tqdm, status: DownloadStatus, dest_path: Path, position: int = None, total: int = None) -> None:
        """Update progress bar with new status and position.
        
        Args:
            pbar: Progress bar to update
            status: DownloadStatus enum value
            dest_path: Path to the file being processed
            position: Current position (bytes downloaded)
            total: Total size (for reset)
        """
        status_str = self._get_status_indicator(status)
        pbar.set_description(f"[{status_str:^10}] {dest_path}")
        if total is not None:
            pbar.reset(total=total)
        if position is not None:
            pbar.n = position
        pbar.refresh()
    
    async def _verify_file_hash(self, dest_path: Path, expected_hash: str, pbar: tqdm, file_size: int) -> Tuple[bool, DownloadStatus]:
        """Verify file hash with progress tracking.
        
        Args:
            dest_path: Path to the file to verify
            expected_hash: Expected hash value
            pbar: Progress bar to update
            file_size: Expected file size
            
        Returns:
            Tuple of (success, status)
        """
        hash_callback = self._create_hash_progress_callback(pbar, dest_path, file_size)
        actual_hash = self.calculate_hash(dest_path, hash_callback)
        
        # Ensure progress bar is at 100% after verification
        pbar.n = file_size
        pbar.refresh()
        
        if actual_hash == "invalid_gzip_file":
            status = DownloadStatus.CORRUPT  # File exists but can't be unzipped
            self._update_progress_bar(pbar, status, dest_path)
            if dest_path.exists():
                dest_path.unlink()
            return False, status
        
        hash_matches = actual_hash.lower() == expected_hash.lower()
        if not hash_matches:
            status = DownloadStatus.HASH  # Hash mismatch
            self._update_progress_bar(pbar, status, dest_path)
            return False, status
        
        status = DownloadStatus.VALID  # File is valid
        self._update_progress_bar(pbar, status, dest_path)
        return True, status
    
    async def download_file(self, url: str, dest: str | Path, file_size: int, expected_hash: str = None) -> bool:
        """Download a single file with progress tracking and retries."""
        if not self.session:
            raise RuntimeError("Downloader must be used as async context manager")
        
        if self.output_dir:
            dest_path = self.output_dir / dest
        else:
            dest_path = Path(dest)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create progress bar only once outside the retry loop
        status = DownloadStatus.NEW  # Default: new download
        start_pos = 0
        status_str = self._get_status_indicator(status)
        desc = f"[{status_str:^10}] {dest_path}"
        pbar = tqdm(total=file_size, initial=start_pos, unit='B', unit_scale=True, desc=desc, leave=True)
       
        for attempt in range(self.max_retries):
            try:
                # Check if file exists and verify size/hash
                if dest_path.exists():
                    current_size = dest_path.stat().st_size
                    
                    # If file is larger than expected, re-download
                    if current_size > file_size:
                        status = DownloadStatus.REDOWN  # File too large, needs re-download
                        dest_path.unlink()
                        start_pos = 0
                    # If file size matches, verify hash
                    elif current_size == file_size and expected_hash:
                        success, status = await self._verify_file_hash(dest_path, expected_hash, pbar, file_size)
                        if success:
                            pbar.close()
                            return True  # File is valid
                        start_pos = 0  # Re-download on hash mismatch or corrupt file
                    # If file is smaller, try to resume download
                    elif current_size < file_size:
                        status = DownloadStatus.RESUME  # Partial file, will resume
                        start_pos = current_size

                # Update progress bar with current status and position
                self._update_progress_bar(pbar, status, dest_path, start_pos, file_size)

                headers = {'Range': f'bytes={start_pos}-'} if start_pos > 0 else {}
                async with self.session.get(url, headers=headers) as response:
                    if start_pos > 0 and response.status != 206:  # Resume failed
                        status = DownloadStatus.REDOWN  # Switch to full re-download
                        start_pos = 0
                        if dest_path.exists():
                            dest_path.unlink()
                        self._update_progress_bar(pbar, status, dest_path, 0, file_size)
                        continue
                    
                    if response.status not in (200, 206):
                        if attempt == self.max_retries - 1:
                            pbar.close()
                            return False
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    
                    mode = 'ab' if start_pos > 0 else 'wb'
                    with open(dest_path, mode) as f:
                        async for chunk in response.content.iter_chunked(self.chunk_size):
                            f.write(chunk)
                            pbar.update(len(chunk))
                    
                    # Only verify hash if file size matches expected size
                    if dest_path.stat().st_size == file_size and expected_hash:
                        success, status = await self._verify_file_hash(dest_path, expected_hash, pbar, file_size)
                        if not success:
                            if attempt < self.max_retries - 1 and status == DownloadStatus.HASH:  # Try one re-download on hash mismatch
                                status = DownloadStatus.REDOWN
                                self._update_progress_bar(pbar, status, dest_path)
                                if dest_path.exists():
                                    dest_path.unlink()
                                start_pos = 0
                                self._update_progress_bar(pbar, status, dest_path, 0, file_size)
                                continue
                            pbar.close()
                            return False
                    
                    status = DownloadStatus.VALID  # Download complete and valid
                    self._update_progress_bar(pbar, status, dest_path)
                    pbar.close()
                    return True
                    
            except Exception as e:
                if attempt == self.max_retries - 1:
                    status = DownloadStatus.ERROR
                    self._update_progress_bar(pbar, status, dest_path)
                    pbar.set_description(f"[{self._get_status_indicator(status):^10}] {str(e)[:50]}...")
                    pbar.close()
                    return False
                
                # Get current file size for resume
                if dest_path.exists():
                    start_pos = dest_path.stat().st_size
                    status = DownloadStatus.RESUME
                else:
                    start_pos = 0
                    status = DownloadStatus.NEW
                
                self._update_progress_bar(pbar, status, dest_path)
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                # Reset with proper initial position
                self._update_progress_bar(pbar, status, dest_path, start_pos, file_size)
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