"""Private transient OSS, signed S3 URLs never reach application clients."""
from urllib.parse import quote

from engines.autodesk_client import (
    AutodeskError,
    config,
    request,
    signed_download,
    signed_put,
)


def bucket_url():
    return f"{config('APS_OSS_BASE_URL').rstrip('/')}/buckets/{quote(config('APS_BUCKET_KEY'), safe='')}"


def object_url(key):
    return f"{bucket_url()}/objects/{quote(key, safe='')}"


async def ensure_bucket():
    response = await request("GET", f"{bucket_url()}/details", accepted=(404,))
    if response.status_code == 404:
        response = await request("POST", f"{config('APS_OSS_BASE_URL').rstrip('/')}/buckets",
            json={"bucketKey": config("APS_BUCKET_KEY"), "policyKey": "transient"}, accepted=(409,))
        if response.status_code == 409:
            response = await request("GET", f"{bucket_url()}/details")
    if response.json().get("policyKey") != "transient":
        raise AutodeskError("bucket_policy", "O armazenamento Autodesk deve ser privado e temporário.", fallback_safe=True)


async def signed_upload(key):
    response = await request("GET", f"{object_url(key)}/signeds3upload", params={"parts": 1, "minutesExpiration": 60})
    data = response.json()
    if len(data.get("urls", [])) != 1 or not data.get("uploadKey"):
        raise AutodeskError("upload_contract", "Preparação do armazenamento Autodesk impossível.", fallback_safe=True)
    return data


async def complete(key, upload_key):
    response = await request("POST", f"{object_url(key)}/signeds3upload", json={"uploadKey": upload_key}, accepted=(400, 409))
    if response.status_code in (400, 409):
        # Completion acknowledgement may have been lost; a finished object is safe to read.
        await request("GET", f"{object_url(key)}/details")


async def download_url(key):
    response = await request("GET", f"{object_url(key)}/signeds3download", params={"minutesExpiration": 60})
    data = response.json()
    if data.get("status") != "complete" or not data.get("url"):
        raise AutodeskError("output_incomplete", "O ficheiro Autodesk não está totalmente guardado.")
    return data["url"]


async def upload_input(key, data):
    upload = await signed_upload(key)
    await signed_put(upload["urls"][0], data)
    await complete(key, upload["uploadKey"])
    return await download_url(key)


async def read_output(key, upload_key):
    await complete(key, upload_key)
    return await signed_download(await download_url(key))


async def delete_objects(*keys):
    failed = []
    for key in keys:
        if not key:
            continue
        try:
            await request("DELETE", object_url(key), accepted=(404,))
        except AutodeskError:
            failed.append(key)
    return not failed