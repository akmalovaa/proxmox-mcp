"""Release metadata that only fails at publish time, checked at test time instead.

The MCP Registry fetches both artifacts to verify ownership, so a version that
disagrees between pyproject.toml, server.json and the OCI tag is only discovered
after PyPI and GHCR have already been published — the tag cannot be moved back.
"""

import json
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "server.json").read_text())
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
VERSION = PYPROJECT["project"]["version"]


def _package(registry_type: str) -> dict:
    return next(p for p in MANIFEST["packages"] if p["registryType"] == registry_type)


def test_every_version_agrees() -> None:
    assert MANIFEST["version"] == VERSION
    assert _package("pypi")["version"] == VERSION
    assert _package("oci")["identifier"].endswith(f":{VERSION}")


def test_oci_package_carries_no_separate_version_fields() -> None:
    """Not in the JSON schema, so `mcp-publisher validate` passes and only the
    server rejects it — which cost a rejected publish on 2.1.1."""
    oci = _package("oci")
    assert "version" not in oci
    assert "registryBaseUrl" not in oci


def test_package_entries_document_the_same_environment() -> None:
    def names(registry_type: str) -> list[str]:
        return [v["name"] for v in _package(registry_type)["environmentVariables"]]

    assert names("pypi") == names("oci")


def test_oci_identifier_matches_the_dockerfile_label() -> None:
    """The registry verifies image ownership through this label."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert f'LABEL io.modelcontextprotocol.server.name="{MANIFEST["name"]}"' in dockerfile


def test_readme_keeps_the_pypi_ownership_marker() -> None:
    """Line 1 of the README becomes the PyPI description, which is how the registry
    verifies the PyPI package."""
    first_line = (ROOT / "README.md").read_text().splitlines()[0]
    assert first_line == f"<!-- mcp-name: {MANIFEST['name']} -->"


def test_documented_environment_matches_the_code() -> None:
    """A variable the code reads but the manifest omits is invisible to anyone
    installing from the registry."""
    import re

    from proxmox_mcp.config import Settings

    documented = {v["name"] for v in _package("pypi")["environmentVariables"]}
    named_in_config = set(
        re.findall(r'"(PROXMOX_[A-Z_]+)"', (ROOT / "src/proxmox_mcp/config.py").read_text())
    )
    # Settings reads its PROXMOX_-prefixed names through pydantic, not os.environ.
    settings_fields = {f"PROXMOX_{field.upper()}" for field in Settings.model_fields}
    assert (named_in_config | settings_fields) <= documented
