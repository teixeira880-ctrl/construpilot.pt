"""Editorially shorten typing/waiting so the real response appears on its narrated cue."""
import json
import shutil
import subprocess

from config import WORK


def sync(orientation):
    folder=WORK/'capture'/orientation;path=folder/'assistant.json'
    meta=json.loads(path.read_text());voice=json.loads((WORK/'voice/assistant.json').read_text())
    if meta.get('sync_voice_hash')==voice['hash']:return
    alignment=voice['alignment'];text=''.join(alignment['characters']).lower()
    cue=alignment['character_start_times_seconds'][text.index('regardez')]
    target=voice['duration']+.5
    source=folder/'assistant.webm';backup=folder/'assistant-original.webm'
    if not backup.exists():
        shutil.copyfile(source,backup);(folder/'assistant-original.json').write_text(path.read_text())
    original=json.loads((folder/'assistant-original.json').read_text())
    marks=original['marks']
    ranges=[(marks['start'],marks['sent']+.2),(max(marks['sent']+.3,marks['response']-.4),marks['end'])]
    allocations=[cue,target-cue]
    chains=[]
    for i,((a,b),d) in enumerate(zip(ranges,allocations)):
        chains.append(f'[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)*{d/(b-a)},fps=30[v{i}]')
    chains.append('[v0][v1]concat=n=2:v=1:a=0,format=yuv420p[v]')
    output=folder/'assistant-sync.webm'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-threads','2','-i',str(backup),'-filter_complex_threads','2','-filter_complex',';'.join(chains),'-map','[v]','-an','-c:v','libvpx-vp9','-threads','2','-deadline','realtime','-cpu-used','5','-crf','20','-b:v','0','-t',str(target),str(output)],check=True)
    output.replace(source)
    meta.update(marks={'start':0,'end':target},sync_voice_hash=voice['hash'],edit_note='Real typing/request/response frames retimed to narration; no fabricated UI. Original capture retained.',original_marks=marks)
    path.write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print('SYNCHRONIZED',orientation,'response cue',round(cue,2),'s',flush=True)


if __name__=='__main__':
    import sys
    sync(sys.argv[1])