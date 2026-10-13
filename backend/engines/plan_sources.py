"""Sources de plans privées : morceaux bornés, empreinte et copie indépendante."""
import base64
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

CHUNK_SIZE = 1024 * 1024
INLINE_LIMIT = 8 * CHUNK_SIZE
MAX_SOURCE_SIZE = 50 * CHUNK_SIZE


def _owner(plan_id, user_id):
    if not plan_id or not user_id:
        raise ValueError("Identidade da planta e da conta obrigatórias")
    return {"plan_id": plan_id, "user_id": user_id}


def _check(data, record):
    if not data or len(data) > MAX_SOURCE_SIZE:
        raise HTTPException(409, "Fonte vazia ou demasiado volumosa: volte a importar as páginas úteis")
    if record.get('size_bytes') is not None and len(data) != record['size_bytes']:
        raise HTTPException(409, "Fonte incompleta: volte a importar a planta")
    if record.get('sha256') and hashlib.sha256(data).hexdigest() != record['sha256']:
        raise HTTPException(409, "Integridade da fonte não verificada: volte a importar a planta")
    return data


async def load_plan_source(db, plan_id, user_id):
    owner = _owner(plan_id, user_id)
    record = await db.plan_sources.find_one(owner, {"_id": 0})
    if not record:
        return None
    try:
        if record.get('chunk_count'):
            expected = record['chunk_count']
            if not isinstance(expected, int) or not 1 <= expected <= MAX_SOURCE_SIZE // CHUNK_SIZE:
                raise ValueError("Número de fragmentos inválido")
            query = {**owner, 'source_generation': record['source_generation']}
            chunks = [c async for c in db.plan_source_chunks.find(query, {'_id': 0}).sort('index', 1).limit(expected+1)]
            if [c['index'] for c in chunks] != list(range(expected)):
                raise ValueError("Fragmento em falta ou duplicado")
            data = b''.join(base64.b64decode(c['data_b64'], validate=True) for c in chunks)
        else:
            data = base64.b64decode(record['data_b64'], validate=True)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(409, "Fonte ilegível ou incompleta: volte a importar a planta") from None
    _check(data, record)
    return {**record, 'data_b64': base64.b64encode(data).decode('ascii')}


async def save_plan_source(db, plan_id, user_id, data, **metadata):
    owner = _owner(plan_id, user_id)
    _check(data, {})
    generation = uuid.uuid4().hex
    previous = await db.plan_sources.find_one(owner, {'_id': 0, 'source_generation': 1})
    reserved = {'plan_id', 'user_id', '_id', 'data_b64', 'source_generation', 'chunk_count', 'size_bytes', 'sha256'}
    record = {k: v for k, v in metadata.items() if k not in reserved}
    record.update(owner, source_generation=generation, size_bytes=len(data),
                  sha256=hashlib.sha256(data).hexdigest(), updated_at=datetime.now(timezone.utc).isoformat())
    if len(data) > INLINE_LIMIT:
        record['chunk_count'] = (len(data)+CHUNK_SIZE-1)//CHUNK_SIZE
    else:
        record['data_b64'] = base64.b64encode(data).decode('ascii')
        record['chunk_count'] = 0
    try:
        if record['chunk_count']:
            for index, start in enumerate(range(0, len(data), CHUNK_SIZE)):
                await db.plan_source_chunks.insert_one({**owner, 'source_generation': generation, 'index': index,
                                                        'data_b64': base64.b64encode(data[start:start+CHUNK_SIZE]).decode('ascii')})
        update = {'$set': record}
        if record['chunk_count']: update['$unset'] = {'data_b64': ''}
        # Publish the metadata only when every new piece is available.
        await db.plan_sources.update_one(owner, update, upsert=True)
    except BaseException:
        # A lost acknowledgement can occur after publication. Never remove
        # pieces still referenced by the metadata, or on an ambiguous DB read.
        try:
            current = await db.plan_sources.find_one(owner, {'_id': 0, 'source_generation': 1})
            if not current or current.get('source_generation') != generation:
                await db.plan_source_chunks.delete_many({**owner, 'source_generation': generation})
        except Exception:
            pass
        raise
    if previous and previous.get('source_generation'):
        await db.plan_source_chunks.delete_many({**owner, 'source_generation': previous['source_generation']})
    return record


async def save_cad_source(db, plan_id, user_id, source_kind, data):
    owner = _owner(plan_id, user_id)
    if source_kind not in ('original', 'converted_dxf'):
        raise ValueError("Fonte CAD desconhecida")
    _check(data, {})
    count = (len(data)+CHUNK_SIZE-1)//CHUNK_SIZE
    digest = hashlib.sha256(data).hexdigest()
    for index, start in enumerate(range(0, len(data), CHUNK_SIZE)):
        await db.plan_cad_sources.insert_one({**owner, 'source_kind': source_kind, 'index': index,
                                              'chunk_count': count, 'size_bytes': len(data), 'sha256': digest,
                                              'data_b64': base64.b64encode(data[start:start+CHUNK_SIZE]).decode('ascii')})


async def load_cad_source(db, plan_id, user_id, source_kind):
    owner = _owner(plan_id, user_id)
    chunks = [c async for c in db.plan_cad_sources.find({**owner, 'source_kind': source_kind}, {'_id': 0})
              .sort('index', 1).limit(MAX_SOURCE_SIZE//CHUNK_SIZE+1)]
    if not chunks:
        return None
    expected = chunks[0].get('chunk_count', len(chunks))  # v2 compatibility
    if len(chunks) > MAX_SOURCE_SIZE//CHUNK_SIZE or [c['index'] for c in chunks] != list(range(expected)):
        raise HTTPException(409, "Fonte CAD incompleta: volte a importar o desenho")
    try:
        data = b''.join(base64.b64decode(c['data_b64'], validate=True) for c in chunks)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(409, "Fonte CAD ilegível: volte a importar o desenho") from None
    return _check(data, chunks[0])


async def delete_plan_sources(db, plan_id, user_id):
    owner = _owner(plan_id, user_id)
    await db.plan_sources.delete_many(owner)
    await db.plan_source_chunks.delete_many(owner)
    await db.plan_cad_sources.delete_many(owner)


async def copy_plan_sources(db, source_id, target_id, user_id):
    source = await load_plan_source(db, source_id, user_id)
    try:
        if source:
            await save_plan_source(db, target_id, user_id, base64.b64decode(source['data_b64']),
                                   **{k: v for k, v in source.items() if k not in ('plan_id', 'user_id', 'data_b64')})
        for kind in ('original', 'converted_dxf'):
            data = await load_cad_source(db, source_id, user_id, kind)
            if data: await save_cad_source(db, target_id, user_id, kind, data)
    except BaseException:
        await delete_plan_sources(db, target_id, user_id)
        raise


def image_plan_pdf(page):
    """Source PDF dans le repère de l'aperçu normalisé (rotation/redressement inclus)."""
    import pymupdf
    dpi = float(page.get('dpi') or 96)
    with pymupdf.open() as pdf:
        target = pdf.new_page(width=page['width_px']*72/dpi, height=page['height_px']*72/dpi)
        target.insert_image(target.rect, stream=base64.b64decode(page['image_png_b64']))
        return pdf.tobytes(garbage=4, deflate=True)
