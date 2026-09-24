"""Prepara una copia Servlet en Tomcat 9 para validate_local_apps.py."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://repo.maven.apache.org/maven2/'


def download(remote, destination):
    response = requests.get(BASE + remote, timeout=60)
    response.raise_for_status()
    digest = requests.get(BASE + remote + '.sha512', timeout=30)
    algorithm = 'sha512'
    if digest.status_code == 404:
        digest = requests.get(BASE + remote + '.sha1', timeout=30)
        algorithm = 'sha1'
    digest.raise_for_status()
    expected = digest.text.strip().split()[0]
    if hashlib.new(algorithm, response.content).hexdigest() != expected:
        raise RuntimeError('Checksum incorrecto: ' + remote)
    destination.write_bytes(response.content)
    print(destination.name, 'checksum OK')
    return response.content


def main():
    work = ROOT / 'evidencias/integracion'
    root = work / 'java-runtime'
    root.mkdir(parents=True, exist_ok=True)
    metadata = requests.get(BASE + 'org/apache/tomcat/tomcat/maven-metadata.xml', timeout=30)
    metadata.raise_for_status()
    versions = [x.text for x in ET.fromstring(metadata.text).findall('.//version')
                if x.text.startswith('9.0.') and x.text.split('.')[-1].isdigit()]
    version = max(versions, key=lambda x: tuple(map(int, x.split('.'))))
    archive_data = download(f'org/apache/tomcat/tomcat/{version}/tomcat-{version}.zip', root / f'tomcat-{version}.zip')
    download('com/h2database/h2/2.2.224/h2-2.2.224.jar', root / 'h2-2.2.224.jar')
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        if not all((root / item).resolve().is_relative_to(root.resolve()) for item in archive.namelist()):
            raise RuntimeError('Ruta inválida en archivo Tomcat')
        archive.extractall(root)
    target = work / 'vulnport-java'
    if not target.exists():
        shutil.copytree(ROOT.parent / 'vulnport-java', target,
                        ignore=shutil.ignore_patterns('.git', 'target'))
    tomcat = root / f'apache-tomcat-{version}'
    (root / 'runtime.json').write_text(json.dumps({'tomcat': tomcat.name}), encoding='utf-8')
    app = tomcat / 'webapps/vulnport-java'
    shutil.copytree(target / 'src/main/webapp', app, dirs_exist_ok=True)
    classes = app / 'WEB-INF/classes'
    classes.mkdir(parents=True, exist_ok=True)
    libs = app / 'WEB-INF/lib'
    libs.mkdir(exist_ok=True)
    shutil.copy2(root / 'h2-2.2.224.jar', libs)
    sources = list((target / 'src/main/java').rglob('*.java'))
    subprocess.run(['javac', '-encoding', 'UTF-8', '-source', '8', '-target', '8',
                    '-cp', str(tomcat / 'lib/servlet-api.jar'), '-d', str(classes),
                    *map(str, sources)], check=True)
    print('Servlets compilados:', len(sources))


if __name__ == '__main__':
    main()
