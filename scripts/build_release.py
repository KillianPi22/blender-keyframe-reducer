"""Build deterministic Blender extension and delivery ZIPs using only stdlib."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'keyframe_reducer'


def package_version():
    manifest = tomllib.loads((PACKAGE / 'blender_manifest.toml').read_text(encoding='utf-8'))
    for node in ast.parse((PACKAGE / '__init__.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in node.targets):
            info = ast.literal_eval(node.value)
            break
    else:
        raise ValueError('Missing bl_info')
    version = manifest['version']
    if version != '.'.join(map(str, info['version'])):
        raise ValueError('Manifest and bl_info versions disagree')
    if manifest['id'] != 'keyframe_reducer':
        raise ValueError('Unexpected extension identity')
    return version


def write_zip(path, entries):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(entries)
        assert all(archive.read(name) == data for name, data in entries.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--check-release-request', action='store_true')
    args = parser.parse_args()
    version = package_version()
    if args.check_release_request:
        requested = json.loads((ROOT / 'release.json').read_text(encoding='utf-8'))['version']
        if requested != version:
            raise ValueError(f'Release request {requested} differs from source version {version}')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    entries = {p.relative_to(PACKAGE).as_posix(): p.read_bytes() for p in PACKAGE.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    required = {'__init__.py', 'core.py', 'engine.py', 'selection.py', 'blender_manifest.toml',
                'LICENSE', 'README_EN.md', 'README_FR.md'}
    if not required.issubset(entries):
        raise ValueError(f'Missing package files: {required - entries.keys()}')
    extension = output / f'keyframe_reducer-{version}.zip'
    write_zip(extension, entries)
    pack_entries = {extension.name: extension.read_bytes(), **{
        name: entries[name] for name in ('README_EN.md', 'README_FR.md', 'LICENSE')}}
    pack_entries['READ_FIRST.md'] = (ROOT / 'docs/PUBLIC_PACK.md').read_bytes()
    source_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    pack_entries['SOURCE_SHA256.json'] = (json.dumps(source_hashes, indent=2, sort_keys=True) + '\n').encode()
    pack = output / f'Keyframe_Reducer_Pack_{version}.zip'
    write_zip(pack, pack_entries)
    artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (extension, pack)}
    checksums = output / 'SHA256SUMS.txt'
    checksums.write_text(''.join(f'{digest}  {name}\n' for name, digest in artifacts.items()), encoding='utf-8')
    print(json.dumps({'version': version, 'source_files': len(entries), 'output': str(output),
                      'artifacts': artifacts, 'checksums': checksums.name}, indent=2))


if __name__ == '__main__':
    main()
