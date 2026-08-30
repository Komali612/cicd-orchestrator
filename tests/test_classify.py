"""Classifier tests — the routing brain. Offline (local trees, no clone)."""
from agent.classify import _classify_csproj, classify_local_tree

FX = '<Project ToolsVersion="15.0"><PropertyGroup><TargetFrameworkVersion>v4.8</TargetFrameworkVersion></PropertyGroup></Project>'
CORE = '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'
CORE_WIN = '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0-windows</TargetFramework></PropertyGroup></Project>'


def _write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_classify_csproj_unit():
    assert _classify_csproj(FX) == "netfx48"
    assert _classify_csproj(CORE) == "netcore"
    assert _classify_csproj(CORE_WIN) == "netcore"
    assert _classify_csproj("<Project></Project>") is None


def test_pure_netfx_repo(tmp_path):
    _write(tmp_path, "App.csproj", FX)
    d = classify_local_tree(str(tmp_path))
    assert d["stack"] == "netfx48"
    assert d["primary_target"] == "App.csproj"


def test_pure_netcore_repo(tmp_path):
    _write(tmp_path, "src/Api/Api.csproj", CORE)
    d = classify_local_tree(str(tmp_path))
    assert d["stack"] == "netcore"


def test_mixed_repo_routes_by_primary_fx_app(tmp_path):
    # The Fiserve shape: an FX web app + an SDK-style installer helper.
    _write(tmp_path, "FiserveDotnetFrameworkTest.csproj", FX)
    _write(tmp_path, "Installer/MsiBuilder/MsiBuilder.csproj", CORE_WIN)
    d = classify_local_tree(str(tmp_path))
    assert d["stack"] == "netfx48"           # installer helper is skipped
    assert d["primary_target"] == "FiserveDotnetFrameworkTest.csproj"


def test_netcore_app_with_test_project_routes_netcore(tmp_path):
    _write(tmp_path, "src/Api/Api.csproj", CORE)
    _write(tmp_path, "tests/Api.Tests/Api.Tests.csproj", CORE)
    d = classify_local_tree(str(tmp_path))
    assert d["stack"] == "netcore"
    assert "test" not in d["primary_target"].lower()


def test_unknown_when_no_project(tmp_path):
    _write(tmp_path, "README.md", "# just docs")
    d = classify_local_tree(str(tmp_path))
    assert d["stack"] == "unknown"
    assert d["primary_target"] is None
