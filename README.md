# ue-commit-gitdeps-cdn

A Python tool to download Unreal Engine dependencies specified in `Commit.gitdeps.xml` and serve them via a static CDN using Nginx.

## Key Features

- Automatically parse `Commit.gitdeps.xml` file to extract dependency URLs
- Asynchronous downloading with configurable concurrency
- Smart local file caching with size management
- SHA-256 hash verification for downloaded files
- Seamless integration with Nginx for static CDN serving

## Requirements

- Python 3.12+
- Nginx
- Sufficient disk space for dependency storage
- Conda (recommended) or pip

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/TommyLau/ue-gitdeps-cdn.git
cd ue-gitdeps-cdn
```

2. Set up the environment:

   Using Conda (recommended):
   ```bash
   # Create and activate the environment
   conda env create -f environment.yml
   conda activate ue-gitdeps-env
   ```

   Using pip:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the download script:
```bash
python main.py path/to/Commit.gitdeps.xml [options]
```

### Command-line Options

```
--workers INT          Number of concurrent downloads (default: 5)
--cache-dir PATH      Directory for cached files (default: ./output)
--max-retries INT     Maximum number of download retries (default: 5)
--timeout INT         Download timeout in seconds (default: 30)
--chunk-size INT      Download chunk size in bytes (default: 8192)
--cache-max-size STR  Maximum cache size (default: 100GB)
--cache-cleanup-threshold INT  Cache cleanup threshold percentage (default: 90)
```

## Cache Management

The tool includes a sophisticated cache management system that:
- Stores downloaded files in a configurable cache directory
- Automatically cleans up old files when cache size exceeds threshold
- Uses access time-based eviction strategy
- Verifies file integrity using SHA-256 hashes

## Configuration

### Nginx Configuration Example

```nginx
server {
    listen 80;
    server_name cdn.example.com;

    root /path/to/cache_dir;
    
    # Disable directory listing
    autoindex off;
    
    location / {
        try_files $uri $uri/ =404;
        # Additional security headers
        add_header X-Content-Type-Options "nosniff";
        add_header X-Frame-Options "DENY";
        add_header X-XSS-Protection "1; mode=block";
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
        return 404;
    }
}
```

## Dependencies

Core dependencies:
- aiohttp >= 3.9.1 (Async HTTP client/server)
- xmltodict >= 0.13.0 (XML parsing)
- tqdm >= 4.65.0 (Progress bars)

Development dependencies:
- black >= 23.7.0 (Code formatting)
- isort >= 5.12.0 (Import sorting)
- mypy >= 1.5.1 (Type checking)

## Security Considerations

- Ensure sufficient disk space for dependency storage
- Configure HTTPS in production environment
- Regularly clean unused cache files (handled automatically)
- Directory listing is disabled by default
- Access to hidden files is blocked
- Security headers are implemented
