"""Read-only TAP transport diagnostic; no scientific selection changes."""
import concurrent.futures
import json

import httpx

from blinkspace.archive import ADQL_TEMPLATE


def probe(job):
    label, method, query = job
    data = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query}
    try:
        with httpx.Client(timeout=90, follow_redirects=True) as client:
            response = client.get("https://irsa.ipac.caltech.edu/TAP/sync", params=data) if method == "GET" else client.post("https://irsa.ipac.caltech.edu/TAP/sync", data=data)
            return {"query": label, "method": method, "status": response.status_code, "bytes": len(response.content), "sample": response.text[:500]}
    except Exception as exc:
        return {"query": label, "method": method, "error": str(exc)}


if __name__ == "__main__":
    queries = {"gaia_one": "SELECT source_id, teff_gspphot FROM gaia_dr3_source WHERE source_id = 4472832130942575872",
               "spherex_top": "SELECT TOP 1 obs_publisher_did, provenance_version FROM spherex.plane",
               "spherex_spatial": ADQL_TEMPLATE.format(ra=269.446269, dec=4.768204)}
    jobs = [(label, method, query) for label, query in queries.items() for method in ("GET", "POST")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for future in concurrent.futures.as_completed([pool.submit(probe, j) for j in jobs]):
            print(json.dumps(future.result()), flush=True)
