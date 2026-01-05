import os
import json
import tempfile
from typing import Dict, Optional

class SonarConnectionCache:
    """Manages temporary caching of SonarQube connection details across multiple hook executions."""
   
    def __init__(self):
        self.cache_file = os.path.join(tempfile.gettempdir(), ".sonar_connection_cache.json")
   
    def store_connection(self, config: Dict[str, str]) -> None:
        """Store SonarQube connection details in temporary cache."""
        cache_data = {
            'host': config['host'],
            'project_key': config['project_key'],
            'token': config['token'],
            'configured_hooks': config['configured_hooks']
        }
       
        # Cache additional properties for default hook
        for key in ['sources', 'exclusions', 'tests', 'test_inclusions']:
            if key in config:
                cache_data[key] = config[key]
       
        # Cache coverage properties
        for key, value in config.items():
            if 'coverage' in key.lower() and 'reportpaths' in key.lower():
                cache_data[key] = value
       
        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f)
   
    def get_connection(self) -> Optional[Dict[str, str]]:
        """Retrieve cached SonarQube connection details."""
        if not os.path.exists(self.cache_file):
            return None
           
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
   
    def clear_cache(self) -> None:
        """Clear the connection cache."""
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
   
    def is_cached(self) -> bool:
        """Check if connection details are cached."""
        return os.path.exists(self.cache_file)