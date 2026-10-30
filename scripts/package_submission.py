"""Build an allowlisted project archive, never including local credentials."""

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('src', 'tests', 'schemas', 'data', 'docs', 'examples', 'scripts')
FILES = ('README.md', 'requirements.txt', '.env.example', '.gitignore')


def main():
    paths = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        paths.extend(path for path in (ROOT / directory).rglob('*') if path.is_file())
    selected = []
    for path in paths:
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            raise ValueError('交付文件不得为符号链接')
        if '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo') or path.name == '.DS_Store':
            continue
        if path.name.startswith('.env') and relative.as_posix() != '.env.example':
            continue
        selected.append(path)
    target = ROOT / 'dist'
    target.mkdir(exist_ok=True)
    manifest = []
    with zipfile.ZipFile(target / 'submission.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(selected)):
            relative = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
            manifest.append({'path': relative, 'sha256': hashlib.sha256(content).hexdigest()})
    (target / 'submission-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'Packaged {len(manifest)} project files; .env, .git and runs are excluded.')


if __name__ == '__main__':
    main()
