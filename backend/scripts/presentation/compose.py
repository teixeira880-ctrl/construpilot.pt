"""Compose four MP4s from actual recorded pages; French captions follow TTS alignment."""
import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import WORK
from story import SCENES, SHORT

FONT = WORK/'fonts/Outfit.ttf'


def font(size): return ImageFont.truetype(str(FONT),size)


def wrap(text, draw, f, width):
    lines=[];line=''
    for word in text.split():
        candidate=(line+' '+word).strip()
        if line and draw.textlength(candidate,font=f)>width:
            lines.append(line);line=word
        else: line=candidate
    return lines+[line] if line else lines


def frame(scene, orientation, index, count, path):
    vertical=orientation=='vertical';w,h=(1080,1920) if vertical else (1920,1080)
    image=Image.new('RGB',(w,h),(12,27,21));d=ImageDraw.Draw(image)
    accent='#b3e348';muted='#b9cfc3';white='#f6fbf7'
    if vertical:
        d.text((46,24),'ConstruPilot',font=font(46),fill=white)
        d.text((46,91),scene['chapter'],font=font(25),fill=accent)
        lines=wrap(scene['title'],d,font(49),988)
        for n,line in enumerate(lines[:2]):d.text((46,133+n*55),line,font=font(49),fill=white)
        box=(24,264,1032,1368)
        footer='Captures réelles · Données de démonstration'
        d.text(((w-d.textlength(footer,font=font(20)))/2,1847),footer,font=font(20),fill=muted)
        if scene.get('notice'):
            for n,line in enumerate(wrap(scene['notice'],d,font(19),990)):
                d.text(((w-d.textlength(line,font=font(19)))/2,1790+n*24),line,font=font(19),fill=accent)
    else:
        d.text((40,13),scene['chapter'],font=font(19),fill=accent)
        d.text((40,45),scene['title'],font=font(40),fill=white)
        logo='ConstruPilot';d.text((w-40-d.textlength(logo,font=font(35)),37),logo,font=font(35),fill=white)
        box=(28,112,1864,832)
        footer='CAPTURES RÉELLES  ·  DONNÉES DE DÉMONSTRATION  ·  SÉQUENCES MONTÉES'
        d.text((40,1054),footer,font=font(13),fill=muted)
        if scene.get('notice'):
            notice=scene['notice'];d.text((w-40-d.textlength(notice,font=font(13)),1054),notice,font=font(13),fill=accent)
    x,y,bw,bh=box
    d.rectangle((x-2,y-2,x+bw+2,y+bh+2),fill='#34483d')
    d.rectangle((x,y,x+bw,y+bh),fill='#112219')
    d.rectangle((0,h-5,round(w*(index+1)/count),h),fill=accent)
    image.save(path)
    return box,(w,h)


def subtitle_groups(meta, max_chars):
    a=meta.get('alignment') or {};chars=a.get('characters',[])
    starts=a.get('character_start_times_seconds',[]);ends=a.get('character_end_times_seconds',[])
    words=[];word='';start=0;end=0
    for c,s,e in zip(chars,starts,ends):
        if c.isspace():
            if word:words.append((word,start,end));word=''
        else:
            if not word:start=s
            word+=c;end=e
    if word:words.append((word,start,end))
    if not words:raise RuntimeError('Narration has no alignment; do not invent subtitle timing')
    groups=[];text='';begin=0;end=0
    for word,s,e in words:
        if text and len(text)+len(word)+1>max_chars:
            groups.append((text,begin,end));text=''
        if not text:begin=s
        text=(text+' '+word).strip();end=e
        if len(text)>28 and text[-1:] in '.!?':groups.append((text,begin,end));text=''
    if text:groups.append((text,begin,end))
    return groups


def ass_time(t):
    cs=round(t*100);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'


def captions(meta, orientation, rate, duration, path):
    w,h=(1080,1920) if orientation=='vertical' else (1920,1080)
    size,margin=(39,183) if orientation=='vertical' else (33,47)
    content=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Outfit,{size},&H00F8FCF9,&H000000FF,&H00101E18,&H900C1B15,-1,0,0,0,100,100,0,0,1,1.3,0,2,55,55,{margin},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    groups=subtitle_groups(meta,65 if orientation=='vertical' else 105)
    for i,(text,start,end) in enumerate(groups):
        start=start/rate+.12;end=min(duration-.05,end/rate+.2)
        if i+1<len(groups):end=min(end,groups[i+1][1]/rate+.12)
        text=text.replace('{','').replace('}','').replace('B T P','BTP').replace('G P T','GPT').replace('D W G','DWG').replace('D X F','DXF').replace('T V A','TVA').replace('P D F','PDF')
        content+=f'Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}\n'
    path.write_text(content,encoding='utf-8')


def clip_intervals(meta):
    marks=meta['marks'];start=max(0,marks.get('start',0));end=marks['end']
    if 'response' in marks and marks['response']-marks.get('sent',marks['response'])>4:
        return [(start,marks['sent']+.7),(max(marks['sent']+.8,marks['response']-1.8),end)]
    return [(start,end)]


def main(orientation, length):
    scenes=SCENES if length=='long' else SHORT
    rate=1.0 if length=='long' else .94
    target=235.0 if length=='long' else 90.0
    base=sum(json.loads((WORK/'voice'/(s['id']+'.json')).read_text())['duration']/rate+.5 for s in scenes)
    if base>target:
        rate*=base/(target-2)
        base=sum(json.loads((WORK/'voice'/(s['id']+'.json')).read_text())['duration']/rate+.5 for s in scenes)
    if not .85<=rate<=1.14:raise RuntimeError('Unnatural narration rate would be required')
    folder=WORK/'render'/f'{length}-{orientation}';folder.mkdir(parents=True,exist_ok=True)
    parts=[];timeline=[];offset=0
    for i,scene in enumerate(scenes):
        sid=scene['id'];source=sid if length=='long' else ('intro' if scene['kind']=='intro' else scene['kind'])
        cap=WORK/'capture'/orientation
        record=json.loads((cap/(source+'.json')).read_text())
        if not record['ok']:raise RuntimeError('Cannot publish a failed capture: '+source)
        meta=json.loads((WORK/'voice'/(sid+'.json')).read_text())
        duration=meta['duration']/rate+.5+(target-base if i==len(scenes)-1 else 0)
        bg=folder/(sid+'.png');box,size=frame(scene,orientation,i,len(scenes),bg)
        subtitles=folder/(sid+'.ass');captions(meta,orientation,rate,duration,subtitles)
        output=folder/(sid+'.mp4');parts.append(output)
        timeline.append({'id':sid,'source':source,'start':round(offset,3),'duration':round(duration,3),'text':scene['text']});offset+=duration
        done=output.with_suffix('.done')
        signature=str((Path(__file__).stat().st_mtime_ns,(cap/(source+'.webm')).stat().st_mtime_ns,meta['hash'],duration,rate))
        if output.exists() and done.exists() and done.read_text()==signature:continue
        intervals=clip_intervals(record);footage_duration=sum(b-a for a,b in intervals)
        streams=[];filters=[]
        for n,(a,b) in enumerate(intervals):
            filters.append(f'[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[c{n}]');streams.append(f'[c{n}]')
        if len(streams)>1:filters.append(''.join(streams)+f'concat=n={len(streams)}:v=1:a=0[cut]')
        else:filters.append('[c0]null[cut]')
        x,y,bw,bh=box;w,h=size
        filters.extend([f'[cut]setpts=(PTS-STARTPTS)*{duration/footage_duration:.8f},fps=30,scale={bw}:{bh}:force_original_aspect_ratio=decrease,pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color=0x112219,setsar=1[ui]',
                        f'[1:v][ui]overlay={x}:{y}:shortest=1,ass={subtitles}:fontsdir={WORK/"fonts"},fade=t=in:st=0:d=0.18,fade=t=out:st={duration-.18:.3f}:d=0.18,format=yuv420p[v]',
                        f'[2:a]atempo={rate:.6f},loudnorm=I=-16:TP=-1.5:LRA=11,adelay=120|120,apad,atrim=0:{duration:.6f},afade=t=out:st={duration-.18:.3f}:d=0.18[a]'])
        cmd=['ffmpeg','-y','-loglevel','error','-threads','2','-filter_complex_threads','2','-i',str(cap/(source+'.webm')),'-loop','1','-framerate','30','-i',str(bg),'-i',str(WORK/'voice'/(sid+'.mp3')),'-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-t',f'{duration:.6f}','-r','30','-c:v','libx264','-threads','2','-preset','fast','-crf','21','-maxrate','2800k','-bufsize','5600k','-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(output)]
        subprocess.run(cmd,check=True)
        done.write_text(signature)
        print('RENDERED',length,orientation,sid,round(duration,2),flush=True)
    listing=folder/'concat.txt';listing.write_text(''.join(f"file '{p}'\n" for p in parts))
    final=WORK/f'ConstruPilot-FR-{length}-{orientation}.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart','-metadata','title=Découvrez ConstruPilot','-metadata','comment=Captures réelles du site, données de démonstration, voix synthétique française ElevenLabs.','-metadata:s:a:0','language=fra',str(final)],check=True)
    (WORK/f'timeline-{length}-{orientation}.json').write_text(json.dumps({'rate':rate,'target_duration':target,'scenes':timeline},ensure_ascii=False,indent=2))
    print('FINAL',final,final.stat().st_size,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--orientation',choices=['horizontal','vertical'],required=True);p.add_argument('--length',choices=['long','short'],required=True)
    a=p.parse_args();main(a.orientation,a.length)