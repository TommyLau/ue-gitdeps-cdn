# ue-commit-gitdeps-cdn

A Python tool to download Unreal Engine dependencies specified in `Commit.gitdeps.xml` and serve them via a static CDN using Nginx.

## Key Features

- Automatically parse `Commit.gitdeps.xml` file to extract dependency URLs
- Asynchronous downloading with configurable concurrency
- Smart local file caching with size management
- Intelligent download resume capability for interrupted transfers
- High-performance SHA-1 hash verification for downloaded files
- Real-time progress tracking for download, decompression, and verification
- Seamless integration with Nginx for static CDN serving

## Requirements

- Python 3.12+
- Nginx
- Sufficient disk space for dependency storage
- Conda (recommended) or pip
- Docker (optional)

## Quick Start

### Using Python Directly

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

### Using Docker

1. Clone the repository:
```bash
git clone https://github.com/TommyLau/ue-gitdeps-cdn.git
cd ue-gitdeps-cdn
```

2. Build the Docker image:
```bash
docker build -t ue-gitdeps-cdn .
```

3. Run the container:
```bash
docker run -v /path/on/host/output:/app/output ue-gitdeps-cdn path/to/Commit.gitdeps.xml [options]
```

Replace `/path/on/host/output` with the directory on your host machine where you want to store the downloaded files.

### Using Pre-built Docker Images

This repository includes GitHub Actions workflows that automatically build and publish Docker images to GitHub Container Registry (GHCR) when changes are pushed.

To use the pre-built image:

```bash
# Pull the latest image
docker pull ghcr.io/tommylau/ue-gitdeps-cdn:latest

# Run the container
docker run --rm -v /path/on/host/output:/app/output ghcr.io/tommylau/ue-gitdeps-cdn:latest path/to/Commit.gitdeps.xml --output-dir /app/output [options]
```

You can also use specific version tags:
```bash
docker pull ghcr.io/tommylau/ue-gitdeps-cdn:v1.0.0
```

### Command-line Options

```
--workers INT          Number of concurrent downloads (default: 5)
--output-dir PATH      Directory for downloaded files (default: ./output)
--max-retries INT     Maximum number of download retries (default: 5)
--timeout INT         Download timeout in seconds (default: 30)
--chunk-size INT      Download chunk size in bytes (default: 8192)
--force-verify        Force verification of all files even if previously verified
--show-stats          Show verification statistics without downloading files
```

### Proxy Configuration

The tool automatically uses system proxy settings from environment variables:
- `HTTP_PROXY` or `http_proxy` for HTTP proxy
- `HTTPS_PROXY` or `https_proxy` for HTTPS proxy
- `NO_PROXY` or `no_proxy` for proxy exclusions

Example usage with proxy:
```bash
# Set proxy environment variables
export http_proxy="http://proxy:8080"
export https_proxy="http://proxy:8080"
export no_proxy="localhost,127.0.0.1"

# Run the program
python main.py path/to/Commit.gitdeps.xml
```

## Download Status Indicators

The tool provides detailed status indicators during the download process:

- `⬇️ NEW` - New file download
- `⏯️ RESUME` - Resuming a partial download
- `📥 REDOWN` - Re-downloading a file (due to size mismatch or failed resume)
- `🔄 UNZIP` - Decompressing gzipped content
- `🔍 VERIFY` - Verifying file hash
- `✅ VALID` - File is valid and verified
- `🔄 CORRUPT` - File exists but can't be unzipped
- `♻️ HASH` - Hash mismatch detected
- `❌ ERROR` - Error during download or verification

## Smart Download Handling

The tool implements intelligent download handling:

- If a file exists and is larger than expected, it will be re-downloaded
- If a file exists but is smaller than expected, download will resume from where it left off
- If a file exists and matches the expected size, hash verification is performed
- Hash verification is performed after decompression for gzipped files
- Real-time progress tracking for both decompression and hash verification phases

## Verification Record System

The tool includes a sophisticated verification record system that:

- Stores verification results in a SQLite database for efficient retrieval
- Maintains exactly one record per file, updating existing records rather than adding new ones
- Skips hash verification for files that haven't changed since last verification
- Tracks file size, modification time, and expected hash to detect changes
- Provides detailed statistics about verification status
- Improves performance by avoiding redundant verifications
- Ensures data integrity by properly flushing the database when the program is interrupted

To use this feature:

- Files are automatically recorded after successful verification
- Use `--force-verify` to verify all files regardless of previous verification
- Use `--show-stats` to display verification statistics without downloading
- The database is stored as `.verification.sqlite3` in your output directory
- If you interrupt the program (Ctrl+C), the database will be properly flushed to prevent data loss

## Configuration

### Nginx Configuration Example

```nginx
server {
    listen 80;
    server_name cdn.example.com;

    root /path/to/output_dir;
    
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

## CI/CD with GitHub Actions

This repository includes GitHub Actions workflows for continuous integration and delivery:

### Docker Image Build and Publish

The workflow automatically builds and publishes Docker images to GitHub Container Registry (GHCR) when:
- Code is pushed to the `main` branch (tagged as `latest`)
- A new tag is created (e.g., `v1.0.0`)
- A pull request is opened against the `main` branch (image is built but not published)

The workflow:
1. Builds the Docker image using the repository's Dockerfile
2. Tags the image with appropriate version information:
   - `latest` tag for the main branch
   - Semantic version tags for releases (e.g., `v1.0.0`, `1.0`)
   - Branch name for feature branches
   - Short commit SHA for all builds
3. Pushes the image to GHCR (except for pull requests)
4. Utilizes caching to speed up subsequent builds

To use this feature:
1. Ensure your repository has the necessary permissions to publish packages
2. Push your changes to the repository
3. Access your Docker images at `ghcr.io/tommylau/ue-gitdeps-cdn`

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
- Directory listing is disabled by default
- Access to hidden files is blocked
- Security headers are implemented
