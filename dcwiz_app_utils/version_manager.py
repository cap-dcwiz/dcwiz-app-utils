import asyncio
import base64
import os
from functools import lru_cache
from pathlib import Path
from typing import Union, Any

from dcwiz_app_utils import get_config, get_api_proxy


@lru_cache
def get_version_manager():
    return VersionManagerClient()


class VersionManagerClient:
    def __init__(self):
        self._locks = {}
        config = get_config()
        api_proxy = get_api_proxy(config)
        self.platform = api_proxy.platform
        self.version_manager_url = config.platform.version_manager_url

        self._cache_path = config.platform.version_manager_cache_path

        if not Path(self._cache_path).exists():
            os.makedirs(self._cache_path, exist_ok=True)

    async def get_node(
        self,
        node_type: str,
        node_id: str,
        fetch_all_files=False,
        files=None,
        cache_files=False,
    ):
        """
        Retrieves information about a node and its associated files.

        Args:
            node_type (str): The class of the node.
            node_id (str): The ID of the node.
            fetch_all_files (bool, optional): Whether to fetch all available files for the node. Defaults to False.
            files (dict, optional): A dictionary of file paths and formats to fetch. Defaults to None.
            cache_files (bool, optional): To cache file to local file storage instead of returning as response. Defaults to False.

        Returns:
            dict: A dictionary containing the node summary and the contents of the fetched files.
        """
        if files is None:
            files = {}
        if fetch_all_files:
            all_files_available = await self.platform.get(
                f"{self.version_manager_url}/{node_type}/{node_id}/files"
            )
            new_files = {}
            for file_path in all_files_available:
                new_files[file_path] = "json"
            files = new_files

        if cache_files:
            await self.fetch_files(node_type, node_id, files)
            file_contents = {}
        else:
            file_contents = await self.platform.parallel_request(
                {
                    file_path: (
                        "get",
                        f"{self.version_manager_url}/{node_type}/{node_id}/files/{file_path}",
                        dict(
                            params={"format": file_format},
                            expect_json=file_format == "json",
                        ),
                    )
                    for file_path, file_format in files.items()
                    if not file_path.startswith(".")
                }
            )

        node_summary = await self.platform.get(
            f"{self.version_manager_url}/{node_type}/{node_id}"
        )

        return node_summary | dict(
            file_contents={k: v for k, v in file_contents.items() if v is not None}
        )

    # Node CRUD Functions
    async def get_nodes(self, node_type: str, **kwargs):
        """
        Retrieve nodes of a given type.
        :param node_type: The type of the node.
        :param kwargs: all the desired filtering/sorting
        :return: list of nodes
        """
        return await self.platform.get(
            url=f"{self.version_manager_url}/{node_type}",
            params={
                "forest": False,
                "compress_group": True,
                **{k: v for k, v in kwargs.items() if v is not None},
            },
        )

    async def create_node(self, node_type: str, body):
        return await self.platform.post(
            url=f"{self.version_manager_url}/{node_type}", json=body
        )

    async def save_as_node(self, node_type: str, node_id: str, body: dict):
        return await self.platform.post(
            url=f"{self.version_manager_url}/{node_type}/{node_id}/save-as", json=body
        )

    async def delete_node(self, node_type: str, node_id: str, skip_dependants=False):
        return await self.platform.delete(
            url=self.version_manager_url + f"/{node_type}/{node_id}",
            params={"dry_run": False, "skip_dependants": skip_dependants},
        )

    async def delete_nodes(self, node_type: str, skip_dependants=False, **kwargs):
        return await self.platform.delete(
            url=self.version_manager_url + f"/{node_type}/multiple_nodes",
            params={"dry_run": False, "skip_dependants": skip_dependants},
            json=kwargs,
        )

    async def duplicate_node(self, node_type: str, node_id: str):
        return await self.platform.post(
            url=f"{self.version_manager_url}/{node_type}/{node_id}/duplicate"
        )

    # Metadata Functions
    async def get_metadata(self, node_type: str, node_id: str):
        return await self.platform.get(
            url=f"{self.version_manager_url}/{node_type}/{node_id}/metadata",
        )

    async def patch_metadata(self, node_type: str, node_id: str, meta_dict=None):
        """

        :param node_type:
        :param node_id:
        :param meta_dict:
        :return:
        """
        if meta_dict is None:
            raise ValueError(
                f"Metadata Patch for [{node_type}]<{node_id}> must be provided"
            )

        return await self.platform.patch(
            url=self.version_manager_url + f"/{node_type}/{node_id}/metadata",
            json=meta_dict,
        )

    async def delete_metadata(
        self,
        node_type: str,
        uuid: str,
        modification_time: Union[float, str],
        keys: list[str],
    ):
        """
        Delete metadata keys for a specific node.

        Args:
            node_type: The type of the node
            uuid: The UUID of the node
            modification_time: The modification time (will be converted to string)
            keys: Dictionary of keys to delete

        Returns:
            The response from the delete operation
        """
        if not isinstance(modification_time, str):
            modification_time = str(modification_time)

        if not keys:
            raise ValueError(
                f"no keys specified for deletion for [{node_type}]<{uuid}>"
            )

        return await self.platform.delete(
            url=self.version_manager_url + f"/{node_type}/{uuid}/metadata",
            json=dict(modification_time=modification_time, keys=keys),
        )

    # Cache & File Management Functions
    async def upload_file(
        self,
        node_type: str,
        node_id: str,
        file_path: str,
        modification_time: Union[float, str],
        content: Any,
        file_format: str = None,
    ):
        """
        Upload a file to the version manager.

        Args:
            node_type: The type of the node
            node_id: The UUID of the node
            file_path: The file path (used to determine format if not specified)
            modification_time: The modification time
            content: The file content to upload
            file_format: Optional file format. If not provided, will be inferred from file_path

        Returns:
            The response from the upload operation
        """
        extension = Path(file_path).suffix.lower()
        if extension != ".json":
            # Handle both string and bytes content
            if isinstance(content, bytes):
                content = base64.b64encode(content).decode()
            else:
                content = base64.b64encode(content.encode()).decode()

        return await self.platform.put(
            url=self.version_manager_url + f"/{node_type}/{node_id}/files/{file_path}",
            json={
                "format": file_format
                if isinstance(file_format, str)
                else extension[1:],
                "content": content,
                "modification_time": str(modification_time),
            },
        )

    async def fetch_files(self, node_type: str, node_id: str, files: dict):
        """
        Downloads File from Experiment Manager if file is not cache locally
        """
        Path(self.cache_path(node_id)).mkdir(exist_ok=True, parents=True)

        requests = []
        for file_path, file_format in files.items():
            if not self._is_cached(node_id, file_path):
                requests.append(
                    (
                        "GET",
                        f"{self.version_manager_url}/{node_type}/{node_id}/files/{file_path}",
                        dict(filename=Path(self.cache_path(node_id, file_path))),
                    )
                )
        await self.platform.parallel_stream(requests)

    def _get_lock(self, uuid):
        """
        Retrieves a lock based on the Node UUID
        """
        if uuid not in self._locks:
            self._locks[uuid] = asyncio.Lock()
        return self._locks[uuid]

    def cache_path(self, uuid, file_path="") -> str:
        """
        Returns a file path for local cache file
        """
        return str(os.path.join(self._cache_path, uuid, file_path))

    def _is_cached(self, uuid, file_path):
        """
        Checks if the file is already cached locally
        """
        return os.path.exists(self.cache_path(uuid, file_path))
