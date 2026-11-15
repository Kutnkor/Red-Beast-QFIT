"""Extract cited, unresampled stellar tracks for the separate evolution explorer.

Run after downloading the upstream files into evidence/evolution-sources.
No observed target is fitted and no values are extrapolated past a table boundary.
"""
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'evidence/evolution-sources'
tracks = []
manifest = []


def record(path, url):
    manifest.append({'file': path.name, 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})


def rounded(row):
    assert all(math.isfinite(x) for x in row)
    return [float(f'{x:.16g}') for x in row]


for mass, filename in [(1, '00100M.track.eep'), (1.4, '00140M.track.eep')]:
    path = SOURCE / filename
    lines = path.read_text(encoding="utf-8").splitlines()
    columns = next(line.lstrip('#').split() for line in lines if line.startswith('#') and 'star_age' in line)
    rows = []
    for line in lines:
        if not line.strip() or line.startswith('#'): continue
        values = dict(zip(columns, map(float, line.split())))
        rows.append(rounded([values['star_age'], 10 ** values['log_Teff'], 10 ** values['log_R'],
                             10 ** values['log_L'], values['star_mass'], values['phase'], abs(values['star_mdot'])]))
    tracks.append({'id': f'mist-{mass}', 'source': 'MIST v1.2', 'mass': mass, 'url': 'https://mist.science/model_grids.html',
                   'composition': '[Fe/H] = 0; v/vcrit = 0', 'rows': rows, 'end': 'WDCS boundary; no subsequent cooling extrapolated'})
    record(path, 'https://mist.science/data/tarballs_v1.2/MIST_v1.2_feh_p0.00_afe_p0.0_vvcrit0.0_EEPS.txz')

path = SOURCE / 'BHAC15_tracks+structure'
rows = []
for line in path.read_text(encoding="utf-8").splitlines():
    try: values = list(map(float, line.split()))
    except ValueError: continue
    if len(values) != 13 or values[0] != .15: continue
    rows.append(rounded([10 ** values[1], values[2], values[5], 10 ** values[3], values[0], -2, 0]))
tracks.append({'id': 'bhac-0.15', 'source': 'BHAC15', 'mass': .15, 'url': 'https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/',
               'composition': 'BHAC15 solar composition', 'rows': rows, 'end': 'Published table endpoint; no terminal phase supplied'})
record(path, 'https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/BHAC15_tracks%2Bstructure')

# ATMO tracks are added below when present; never substitute a warmer grid for WISE 0855.
for mass, name in [(0.005, 'atmo-0.005.txt'), (0.05, 'atmo-0.05.txt')]:
    path = SOURCE / name
    if not path.exists(): continue
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try: values = list(map(float, line.split()))
        except ValueError: continue
        if len(values) < 6: continue
        # ATMO: M/Msun, age/Gyr, Teff/K, log L/Lsun, R/Rsun, log g.
        if values[2] >= 2000: continue
        rows.append(rounded([values[1] * 1e9, values[2], values[4], 10 ** values[3], values[0], -3, 0]))
    tracks.append({'id': f'atmo-{mass}', 'source': 'ATMO 2020 CEQ', 'mass': mass,
                   'url': 'https://perso.ens-lyon.fr/isabelle.baraffe/ATMO2020/',
                   'composition': 'Solar composition; equilibrium chemistry; Teff < 2000 K',
                   'rows': rows, 'end': 'Published cooling table endpoint; no extrapolation'})
    record(path, 'https://perso.ens-lyon.fr/isabelle.baraffe/ATMO2020/ATMO_2020_models.tar.gz')

for track in tracks:
    assert len(track['rows']) > 10
    assert all(a[0] < b[0] for a, b in zip(track['rows'], track['rows'][1:]))
    assert all(all(v > 0 for v in row[:5]) for row in track['rows'])
output = ROOT / 'frontend/src/three/data/evolution.json'
output.write_text(json.dumps({'schema': 1, 'columns': ['age_yr', 'teff_k', 'radius_solar', 'luminosity_solar', 'mass_solar', 'phase', 'mass_loss_solar_per_yr'],
                             'classification': 'theoretical_comparison_not_target_fit', 'sources': manifest, 'tracks': tracks}, separators=(',', ':')) + '\n')
print(json.dumps({'tracks': [(t['id'], len(t['rows'])) for t in tracks], 'bytes': output.stat().st_size}))
