"""Publish explicitly reviewed, nonpersonal MP4s to durable existing object storage."""
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from config import WORK
from engines import storage
from engines.presentation_assets import CACHE, MAX_BYTES
from pymongo import MongoClient


def main():
    approval=WORK/'quality-approved.json'
    if not approval.exists(): raise RuntimeError('Review videos and approve before making them public')
    approved=json.loads(approval.read_text())
    db=MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    if not storage.init_storage():raise RuntimeError('Storage unavailable; do not publish local-only files')
    CACHE.mkdir(parents=True,exist_ok=True)
    for length in ('long','short'):
        for orientation in ('horizontal','vertical'):
            variant=f'{length}-{orientation}'
            path=WORK/f'ConstruPilot-FR-{length}-{orientation}.mp4'
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if approved.get(variant)!=sha: raise RuntimeError('Video changed since approval: '+variant)
            size=path.stat().st_size
            if not 0<size<=MAX_BYTES: raise RuntimeError('Video outside supported size')
            meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))
            v=next(s for s in meta['streams'] if s['codec_type']=='video')
            previous=db.presentation_assets.find_one({'variant':variant,'sha256':sha},{'_id':0})
            parts=previous.get('parts',[]) if previous else []
            if not parts:
                with path.open('rb') as f:
                    index=0
                    while block:=f.read(8*1024*1024):
                        key=f'{storage.APP_NAME}/presentation/fr/{sha}/part-{index:03}.bin'
                        storage.put_object(key,block,'application/octet-stream')
                        verified,_=storage.get_object(key)
                        if hashlib.sha256(verified).digest()!=hashlib.sha256(block).digest():raise RuntimeError('Uploaded part checksum mismatch')
                        parts.append(key);index+=1
            record={'variant':variant,'title':'Découvrez ConstruPilot','duration':float(meta['format']['duration']),
                    'width':v['width'],'height':v['height'],'byte_size':size,'sha256':sha,'parts':parts,
                    'audio_language':'fr-FR','voice_disclosure':'Voix de synthèse ElevenLabs — Nicolas, français parisien',
                    'published':True,'published_at':datetime.now(timezone.utc).isoformat()}
            db.presentation_assets.update_one({'variant':variant},{'$set':record},upsert=True)
            shutil.copyfile(path,CACHE/f'{sha}.mp4')
            print('PUBLISHED',variant,round(size/1024/1024,2),'MB',round(record['duration'],2),'seconds',flush=True)


if __name__=='__main__': main()