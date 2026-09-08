"""Location lookup via Open-Meteo, location data by GeoNames."""
import json
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .config import Config


def request(endpoint, params):
    url = 'https://geocoding-api.open-meteo.com/v1/' + endpoint + '?' + urlencode(params)
    try:
        with urlopen(Request(url, headers={'User-Agent': 'adzan-cli/1.0'}), timeout=10) as response:
            data = json.loads(response.read(1_000_000))
        if not isinstance(data, dict) or data.get('error'):
            raise ValueError('Respons lokasi tidak valid.')
        return data
    except (OSError, ValueError) as e:
        raise ValueError('Pencarian lokasi gagal. Periksa internet atau gunakan --latitude, --longitude, --timezone.') from e


def validate(row):
    try:
        Config(latitude=row['latitude'], longitude=row['longitude'], timezone=row['timezone'])
        if type(row['id']) is not int or not isinstance(row['name'], str) or not row['name']:
            raise ValueError('ID/nama tidak valid.')
        return {k: row[k] for k in ('id', 'name', 'latitude', 'longitude', 'timezone')} | {
            k: str(row.get(k, '')) for k in ('admin1', 'country')}
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError('Data lokasi tidak lengkap atau tidak valid.') from e


def search(name, country=None):
    if len(name.strip()) < 2:
        raise ValueError('Ketik minimal dua karakter nama kota.')
    params = {'name': name.strip(), 'count': 20, 'language': 'id', 'format': 'json'}
    if country:
        if len(country) != 2 or not country.isalpha():
            raise ValueError('Kode negara harus dua huruf, contoh ID.')
        params['countryCode'] = country.upper()
    rows = request('search', params).get('results', [])
    if not isinstance(rows, list):
        raise ValueError('Daftar lokasi tidak valid.')
    return [validate(row) for row in rows]


def by_id(location_id):
    if location_id <= 0:
        raise ValueError('ID lokasi harus positif.')
    row = validate(request('get', {'id': location_id}))
    if row['id'] != location_id:
        raise ValueError('ID hasil lokasi tidak cocok.')
    return row


def show(rows):
    for i, row in enumerate(rows, 1):
        label = ', '.join(filter(None, (row['name'], row['admin1'], row['country'])))
        print(f"{i}. {label} | {row['timezone']} | ID {row['id']}")
        print(f"   {row['latitude']}, {row['longitude']} — adzan-cli configure --location-id {row['id']}")
    if not rows:
        print('Lokasi tidak ditemukan. Coba nama kota lain atau hapus filter negara.')


def choose(name, country=None):
    rows = search(name, country)
    if not rows:
        raise ValueError('Lokasi tidak ditemukan. Coba nama kota lain.')
    show(rows)
    if len(rows) == 1:
        return rows[0]
    if not sys.stdin.isatty():
        raise ValueError('Ada beberapa lokasi. Pilih ID dengan configure --location-id ID.')
    try:
        index = int(input('Pilih nomor lokasi: ')) - 1
    except (ValueError, EOFError) as e:
        raise ValueError('Pilihan lokasi dibatalkan/tidak valid.') from e
    if not 0 <= index < len(rows):
        raise ValueError('Nomor lokasi di luar daftar.')
    return rows[index]


def fields(row):
    return {'location': row['name'], 'latitude': row['latitude'],
            'longitude': row['longitude'], 'timezone': row['timezone']}
