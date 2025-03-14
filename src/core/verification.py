"""Verification record management using SQLite."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class SQLiteVerificationManager:
    """Manage file verification records using SQLite database."""
    
    def __init__(self, base_dir: Path, force_verify: bool = False):
        """Initialize the SQLite verification record manager.
        
        Args:
            base_dir: Base directory for verification records and downloaded files
            force_verify: Whether to force verification regardless of records
        """
        self.base_dir = base_dir
        self.force_verify = force_verify
        self.db_path = base_dir / '.verification.db'
        
        # Ensure the database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-local storage for database connections
        self.local = threading.local()
        
        # Initialize database
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(str(self.db_path))
            # Enable foreign keys and other pragmas
            self.local.connection.execute('PRAGMA foreign_keys = ON')
            self.local.connection.execute('PRAGMA journal_mode = WAL')  # Write-Ahead Logging for better concurrency
            
            # Enable returning rows as dictionaries
            self.local.connection.row_factory = sqlite3.Row
        
        return self.local.connection
    
    def _init_database(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create tables and indexes
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_files (
            file_path TEXT PRIMARY KEY,
            file_size INTEGER NOT NULL,
            modified_time REAL NOT NULL,
            expected_hash TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            verification_status TEXT NOT NULL
        )
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_verified_at 
        ON verified_files(verified_at)
        ''')
        
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_verification_status 
        ON verified_files(verification_status)
        ''')
        
        conn.commit()
    
    def update_record(self, file_path: Path, expected_hash: str, status: str = 'VALID') -> None:
        """Update or create a verification record for a file.
        
        This method will replace any existing record for the file with a new one.
        Each file has exactly one record in the database, identified by its relative path.
        
        Args:
            file_path: Path to the verified file
            expected_hash: Expected hash value
            status: Verification status (VALID, CORRUPT, HASH_MISMATCH)
        """
        try:
            rel_path = str(file_path.relative_to(self.base_dir))
            stat = file_path.stat()
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Using INSERT OR REPLACE ensures we only have one record per file
            # If a record with the same file_path exists, it will be replaced
            cursor.execute('''
            INSERT OR REPLACE INTO verified_files 
            (file_path, file_size, modified_time, expected_hash, verified_at, verification_status)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                rel_path,
                stat.st_size,
                stat.st_mtime,
                expected_hash,
                datetime.now().isoformat(),
                status
            ))
            
            conn.commit()
        except Exception as e:
            print(f"Warning: Could not update verification record: {e}")
    
    # Alias for backward compatibility
    add_record = update_record
    
    def is_verification_needed(self, file_path: Path, expected_hash: str) -> bool:
        """Check if a file needs verification based on records.
        
        Args:
            file_path: Path to the file to check
            expected_hash: Expected hash value
            
        Returns:
            True if verification is needed, False otherwise
        """
        if self.force_verify:
            return True
        
        try:
            rel_path = str(file_path.relative_to(self.base_dir))
            stat = file_path.stat()
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Query for existing record
            cursor.execute('''
            SELECT file_size, modified_time, expected_hash, verification_status
            FROM verified_files
            WHERE file_path = ?
            ''', (rel_path,))
            
            record = cursor.fetchone()
            
            # If no record exists, verification is needed
            if not record:
                return True
            
            # If hash doesn't match record, verification is needed
            if record['expected_hash'] != expected_hash:
                return True
            
            # If file size changed, verification is needed
            if record['file_size'] != stat.st_size:
                return True
            
            # If modification time changed (with small tolerance), verification is needed
            if abs(record['modified_time'] - stat.st_mtime) > 0.001:
                return True
            
            # If previous verification failed, verification is needed
            if record['verification_status'] != 'VALID':
                return True
            
            # File matches record and was previously valid, no verification needed
            return False
            
        except Exception as e:
            # If any error occurs while checking, verify to be safe
            print(f"Warning: Error checking verification record: {e}")
            return True
    
    def get_statistics(self) -> dict:
        """Get statistics about verification records.
        
        Returns:
            Dictionary with statistics
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Total records
            cursor.execute('SELECT COUNT(*) FROM verified_files')
            total_records = cursor.fetchone()[0]
            
            # Records by status
            cursor.execute('''
            SELECT verification_status, COUNT(*) as count
            FROM verified_files
            GROUP BY verification_status
            ''')
            status_counts = {row['verification_status']: row['count'] for row in cursor.fetchall()}
            
            # Recent verifications (last 24 hours)
            recent_cutoff = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()
            cursor.execute('''
            SELECT COUNT(*) FROM verified_files
            WHERE verified_at > ?
            ''', (recent_cutoff,))
            recent_count = cursor.fetchone()[0]
            
            return {
                'total_records': total_records,
                'status_counts': status_counts,
                'recent_verifications': recent_count,
                'database_size_bytes': self.db_path.stat().st_size if self.db_path.exists() else 0
            }
            
        except Exception as e:
            print(f"Warning: Error getting statistics: {e}")
            return {'error': str(e)}
    
    def close(self) -> None:
        """Close database connections."""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()
            del self.local.connection 