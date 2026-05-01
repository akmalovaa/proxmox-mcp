import json
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP

from proxmox_mcp.tools._common import _ctx, _status_response, _tier

ContentType = Literal["iso", "backup", "images", "rootdir", "vztmpl"]
ChecksumAlgorithm = Literal["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_storage(ctx: Context, node: str | None = None) -> str:
        """List storage pools with usage info. Optionally filter by node.

        Args:
            node: Filter by node name. If omitted, lists all cluster storage.
        """
        pve = _ctx(ctx).proxmox
        storage = pve.nodes(node).storage.get() if node else pve.storage.get()
        return json.dumps(storage, indent=2)

    @mcp.tool()
    def get_storage_content(
        ctx: Context, node: str, storage: str, content: ContentType | None = None
    ) -> str:
        """List contents of a storage pool (ISOs, disk images, backups, etc).

        Args:
            node: Node name
            storage: Storage pool name (e.g. 'local', 'local-lvm')
            content: Filter by content type: 'iso', 'backup', 'images', 'rootdir', 'vztmpl'
        """
        pve = _ctx(ctx).proxmox
        params = {}
        if content:
            params["content"] = content
        items = pve.nodes(node).storage(storage).content.get(**params)
        return json.dumps(items, indent=2)

    @mcp.tool()
    def download_iso(
        ctx: Context,
        node: str,
        storage: str,
        url: str,
        filename: str,
        checksum: str | None = None,
        checksum_algorithm: ChecksumAlgorithm | None = None,
    ) -> str:
        """Download an ISO image from a URL into a storage pool.

        Returns a UPID; poll get_task_status(node, upid) to monitor progress.
        Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name where the storage is accessible
            storage: Storage pool name (must support 'iso' content type, e.g. 'local')
            url: HTTP(S) URL to download from
            filename: Target filename (must end with .iso, e.g. 'debian-12.iso')
            checksum: Optional checksum value to verify after download
            checksum_algorithm: Required if checksum is set. One of:
                md5, sha1, sha224, sha256, sha384, sha512
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        params: dict[str, Any] = {
            "url": url,
            "content": "iso",
            "filename": filename,
        }
        if checksum:
            params["checksum"] = checksum
        if checksum_algorithm:
            params["checksum-algorithm"] = checksum_algorithm
        upid = pve.nodes(node).storage(storage)("download-url").post(**params)
        return _status_response("downloading", upid)

    @mcp.tool()
    def delete_iso(ctx: Context, node: str, storage: str, volid: str) -> str:
        """Delete an ISO from a storage pool. Requires PROXMOX_RISK_LEVEL=all.

        Args:
            node: Node name where the storage is accessible
            storage: Storage pool name
            volid: Volume ID as returned by get_storage_content
                (e.g. 'local:iso/debian-12.iso')
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).storage(storage).content(volid).delete()
        return _status_response("deleting_iso", upid)
