"""Real Chromium recordings, including actual typing/clicks. No fabricated UI frames."""
import argparse
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright

from actor import INIT, Actor
from config import BASE, WORK, api_session, read_state
from scenes import perform
from story import SCENES


async def main(orientation, only):
    state=read_state()
    if not state.get('quote_id') or not state.get('analysis_done'): raise RuntimeError('Prepare demo first')
    out=WORK/'capture'/orientation;out.mkdir(parents=True,exist_ok=True)
    viewport={'width':1600,'height':720} if orientation=='horizontal' else {'width':540,'height':780}
    sessions={role:api_session(role)[1] for role in ('pro','admin')}
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        for scene in SCENES:
            sid=scene['id'];meta=out/(sid+'.json')
            if only and sid not in only: continue
            if meta.exists() and json.loads(meta.read_text()).get('ok') and json.loads(meta.read_text()).get('capture_version')==2:
                print('CACHED',orientation,sid,flush=True);continue
            auth=sessions['admin' if sid=='autocad' else 'pro']
            context=await browser.new_context(viewport=viewport,record_video_dir=str(out/'raw'),record_video_size=viewport,locale='fr-FR',color_scheme='light',reduced_motion='no-preference')
            await context.add_init_script("localStorage.setItem('construpilot_token',"+json.dumps(auth['token'])+");"+INIT)
            # Even accidental clicks cannot send physical mail, email, or start payment/Autodesk work.
            blocked=[]
            async def safety(route):
                req=route.request;path=req.url.split('/api/',1)[-1]
                if req.method!='GET' and any(x in path for x in ('/send','postal/send','checkout','payment','/sign','einvoice','pdp/','cad/reprocess')):
                    blocked.append(path);await route.abort();return
                await route.continue_()
            await context.route('**/api/**',safety)
            started=time.monotonic();page=await context.new_page();actor=Actor(page,started)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            video=page.video;ok=False;error=None
            try:
                await perform(actor,scene,state)
                minimum=json.loads((WORK/'voice'/(sid+'.json')).read_text())['duration']+1.7
                elapsed=time.monotonic()-started-actor.marks.get('start',0)
                await actor.settle(max(0,minimum-elapsed))
                actor.mark('end')
                await page.screenshot(path=str(out/(sid+'.jpg')),type='jpeg',quality=55,full_page=False)
                if blocked: raise RuntimeError('Safety route blocked an unexpected action: '+str(blocked))
                if errors: raise RuntimeError('Browser errors: '+str(errors[:3]))
                ok=True
            except Exception as exc:
                error=str(exc);actor.mark('end')
                await page.screenshot(path=str(out/(sid+'_error.jpg')),type='jpeg',quality=55,full_page=False)
                print('FAILED',orientation,sid,error,flush=True)
            await context.close()
            destination=out/(sid+'.webm')
            temporary=out/(sid+'.recording.webm')
            await video.save_as(str(temporary))
            temporary.replace(destination)
            await video.delete()
            meta.write_text(json.dumps({'capture_version':2,'ok':ok,'error':error,'scene':sid,'orientation':orientation,'marks':actor.marks,'viewport':viewport,'blocked_actions':blocked},ensure_ascii=False,indent=2))
            print('RECORDED',orientation,sid,ok,actor.marks,flush=True)
            if not ok and sid in ('assistant','quote','measure','autocad'): break
        await browser.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--orientation',choices=['horizontal','vertical'],required=True);p.add_argument('--only',nargs='*')
    args=p.parse_args();asyncio.run(main(args.orientation,args.only))