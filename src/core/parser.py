"""Parser module for Commit.gitdeps.xml files."""

from typing import List, Dict
import xmltodict
from pathlib import Path
import traceback


class GitDepsParser:
    """Parse Commit.gitdeps.xml file to extract dependency information."""
    
    def __init__(self, xml_path: str | Path):
        """Initialize the parser with XML file path."""
        self.xml_path = Path(xml_path)
    
    async def parse(self) -> List[Dict]:
        """Parse XML and return list of dependency information."""
        if not self.xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {self.xml_path}")
        
        try:
            with open(self.xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                data = xmltodict.parse(content)
                return self._extract_dependencies(data)
            except Exception as e:
                print(f"XML parsing error: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
                raise ValueError(f"Failed to parse XML file: {e}")
        except Exception as e:
            print(f"File reading error: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            raise
    
    def _extract_dependencies(self, data: Dict) -> List[Dict]:
        """Extract dependency information from parsed XML data."""
        try:
            packs = data['DependencyManifest']['Packs']['Pack']
            base_url = data['DependencyManifest']['@BaseUrl']
            
            if not isinstance(packs, list):
                packs = [packs]
            
            dependencies = []
            for pack_info in packs:
                remote_path = pack_info['@RemotePath'].strip('/')
                file_hash = pack_info['@Hash']
                
                dep = {
                    'hash': file_hash,
                    'size': int(pack_info['@Size']),
                    'compressed_size': int(pack_info['@CompressedSize']),
                    'remote_path': remote_path,
                    'url': f"{base_url}/{remote_path}/{file_hash}",
                    'dest': f"{remote_path}/{file_hash}"
                }
                dependencies.append(dep)
            
            return dependencies
        except KeyError as e:
            print(f"Missing required key in XML: {e}")
            raise ValueError(f"Invalid XML structure: missing {e}")
        except Exception as e:
            print(f"Error extracting dependencies: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Failed to extract dependencies: {e}") 