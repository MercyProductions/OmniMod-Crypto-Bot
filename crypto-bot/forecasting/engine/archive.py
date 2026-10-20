"""Bounded official Binance archive downloads, SHA-256 sidecars and explicit units."""
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

MAX_ZIP = 40_000_000


def retrieve(url, limit=MAX_ZIP):
    request = urllib.request.Request(url, headers={'User-Agent': 'OmniModResearch/1.0'})
    with urllib.request.urlopen(request, timeout=40) as response:
        if response.geturl().split('/')[2] != 'data.binance.vision':
            raise ValueError('unexpected_archive_redirect')
        body = response.read(limit+1)
        if len(body) > limit: raise ValueError('archive_response_too_large')
        return body


def download(pair, month, directory):
    if not re.fullmatch(r'[A-Z0-9]{4,24}', pair) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', month):
        raise ValueError('invalid_archive_identity')
    name = f'{pair}-1m-{month}.zip'
    url = f'https://data.binance.vision/data/spot/monthly/klines/{pair}/1m/{name}'
    folder = Path(directory); folder.mkdir(parents=True, exist_ok=True)
    target = folder/name
    expected = retrieve(url+'.CHECKSUM', 4096).decode().split()[0].lower()
    if not re.fullmatch(r'[0-9a-f]{64}', expected): raise ValueError('invalid_checksum_sidecar')
    body = target.read_bytes() if target.exists() else retrieve(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected: raise ValueError('archive_checksum_mismatch')
    if not target.exists(): target.write_bytes(body)
    manifest = {'provider': 'Binance Public Data', 'pair': pair, 'interval': '1m', 'month': month,
                'url': url, 'sha256': actual, 'license': 'Binance data terms; not a redistribution grant',
                'timestampUnits': 'microseconds if >= 1e14, otherwise milliseconds',
                'scope': 'Explicit requested pair/month, not survivorship-free market sampling'}
    (folder/(name+'.manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def load_archive(file):
    with zipfile.ZipFile(file) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].file_size > 150_000_000 or not members[0].filename.endswith('.csv'):
            raise ValueError('unexpected_archive_members')
        with archive.open(members[0]) as stream:
            for row in csv.reader(io.TextIOWrapper(stream, encoding='utf-8')):
                if not row or row[0] in ('open_time', 'Open time'): continue
                stamp = int(row[0]); stamp = stamp//1000 if stamp >= 100_000_000_000_000 else stamp
                yield {'time': stamp, 'open': float(row[1]), 'high': float(row[2]), 'low': float(row[3]),
                       'close': float(row[4]), 'volume': float(row[5]), 'quote_volume': float(row[7]),
                       'trades': int(row[8]), 'taker_buy_volume': float(row[9])}
