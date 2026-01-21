import json
import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FileAuthStore:
    def __init__(self, directory: str):
        """
        Initialize the FileAuthStore with a directory to store authentication tokens.

        Args:
            directory: The directory path where auth tokens will be stored
        """
        self.directory = directory
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Initialized FileAuthStore with directory: {directory}")

    def _get_path(self, key: str) -> str:
        """
        Get the file path for a given key.

        Args:
            key: The authentication key (typically username)

        Returns:
            The full file path for the key
        """
        return os.path.join(self.directory, f"{key}.json")

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the store by key.

        Args:
            key: The key to retrieve

        Returns:
            The stored value or None if not found or error occurs
        """
        try:
            path = self._get_path(key)
            if not os.path.exists(path):
                logger.debug(f"No file found for key: {key}")
                return None

            with open(path, "r") as f:
                data = json.load(f)
                logger.debug(f"Successfully retrieved data for key: {key}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for key {key}: {e}")
            return None
        except IOError as e:
            logger.error(f"IO error reading file for key {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving data for key {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        Store a value with the given key.

        Args:
            key: The key to store the value under
            value: The value to store

        Returns:
            True if successful, False otherwise
        """
        try:
            path = self._get_path(key)
            with open(path, "w") as f:
                json.dump(value, f, indent=2)
            logger.info(f"Successfully stored data for key: {key}")
            return True
        except (IOError, TypeError) as e:
            logger.error(f"Error storing data for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing data for key {key}: {e}")
            return False
