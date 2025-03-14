"""Cache management for downloaded files."""

import hashlib
import shutil
from pathlib import Path
from typing import Optional


def parse_size(size_str: str) -> int:
    """Convert size string (e.g., '100GB') to bytes."""
    units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    size = size_str.strip().upper()  # 转换为大写以统一处理
    
    # 处理没有单位的情况
    if size.isdigit():
        return int(size)
    
    # 查找数字部分和单位部分
    for unit, multiplier in units.items():
        if size.endswith(unit.upper()):
            try:
                number = float(size[:-len(unit)])
                return int(number * multiplier)
            except ValueError:
                continue
    
    raise ValueError(f"Invalid size format: {size_str}")


class CacheManager:
    """Manage local file cache for downloaded dependencies."""
    
    def __init__(self, cache_dir: str | Path, max_size: str = "100GB",
                 cleanup_threshold: int = 90):
        """Initialize cache manager with configuration parameters."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = parse_size(max_size)
        self.cleanup_threshold = cleanup_threshold / 100.0
    
    def get_cache_size(self) -> int:
        """Calculate total size of cached files."""
        total_size = 0
        for file_path in self.cache_dir.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size
    
    def cleanup_cache(self) -> None:
        """Remove oldest files when cache exceeds threshold."""
        current_size = self.get_cache_size()
        if current_size <= self.max_size * self.cleanup_threshold:
            return
        
        # Get files sorted by access time
        files = [(f, f.stat().st_atime) for f in self.cache_dir.rglob('*') if f.is_file()]
        files.sort(key=lambda x: x[1])  # Sort by access time
        
        # Remove oldest files until we're under threshold
        for file_path, _ in files:
            if current_size <= self.max_size * self.cleanup_threshold:
                break
            size = file_path.stat().st_size
            file_path.unlink()
            current_size -= size
    
    def get_cached_file(self, file_path: str) -> Optional[Path]:
        """Check if file exists in cache by its path."""
        cached_path = self.cache_dir / file_path
        if cached_path.exists():
            return cached_path
        return None
    
    def add_to_cache(self, source_file: str | Path, dest_path: str) -> Path:
        """
        Add downloaded file to cache.
        
        Args:
            source_file: The temporary downloaded file path
            dest_path: The destination path relative to cache directory (e.g. 'remote_path/hash')
        """
        source_path = Path(source_file)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        cached_path = self.cache_dir / dest_path
        if not cached_path.exists():
            # Check cache size and cleanup if necessary
            self.cleanup_cache()
            # Create parent directories if they don't exist
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy file to cache
            shutil.copy2(source_path, cached_path)
        
        return cached_path
    
    def calculate_hash(self, file_path: str | Path) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest() 