import asyncio
import json
import time

from config import BASE, WORK

INIT = r"""
localStorage.setItem('construpilot_lang','fr');
localStorage.setItem('cp_cookie_consent','refused');
localStorage.setItem('construpilot_cookie_consent','rejected');
localStorage.setItem('construpilot-cookie-consent','rejected');
localStorage.setItem('theme','light');
function initPresentation(){
  const style=document.createElement('style');
  style.textContent=`*{scroll-behavior:smooth!important} [data-testid^="radar-permit-field-adresse"],[data-testid^="radar-permit-field-nom"],[data-testid^="radar-permit-field-declarant"],[data-testid="workspace-account-menu"],a[href^="mailto:"],input[type="email"]{filter:blur(7px)!important} #presentation-pointer{position:fixed;width:25px;height:33px;pointer-events:none;z-index:2147483646;left:50%;top:45%;filter:drop-shadow(0px 1px 2px #0008)} #presentation-click{position:fixed;width:34px;height:34px;border:3px solid #9bdc39;border-radius:50%;pointer-events:none;z-index:2147483647;opacity:0;transform:translate(-50%,-50%);transition:opacity .2s} [data-testid="cookie-banner"]{display:none!important}`;
  document.head.appendChild(style);
  const cursor=document.createElement('div');cursor.id='presentation-pointer';cursor.innerHTML='<svg viewBox="0 0 25 33"><path d="M2 2 L2 27 L8 21 L13 31 L18 28 L12 18 L22 18 Z" fill="#101a16" stroke="white" stroke-width="2"/></svg>';
  document.body.appendChild(cursor);
  const ring=document.createElement('div');ring.id='presentation-click';document.body.appendChild(ring);
  document.addEventListener('mousemove',e=>{cursor.style.left=e.clientX+'px';cursor.style.top=e.clientY+'px';cursor.style.opacity=e.target.dataset?.cursorMode==='high-contrast-measure'?'0':'1';});
  document.addEventListener('mousedown',e=>{ring.style.left=e.clientX+'px';ring.style.top=e.clientY+'px';ring.style.opacity='1';setTimeout(()=>ring.style.opacity='0',360);});
  function redact(){const walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=walk.nextNode()){if(['SCRIPT','STYLE','TEXTAREA'].includes(n.parentElement?.tagName))continue;const v=n.nodeValue;const next=v.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,'[adresse masquée]').replace(/(?<![\w\d])(?:\+33\s?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)/g,'[téléphone masqué]');if(next!==v)n.nodeValue=next;}}
  new MutationObserver(redact).observe(document.body,{subtree:true,childList:true,characterData:true});redact();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initPresentation);else initPresentation();
"""


class Actor:
    def __init__(self, page, start):
        self.p=page; self.start=start; self.marks={}

    def mark(self, name): self.marks[name]=time.monotonic()-self.start

    async def cue(self, scene, phrase):
        meta=json.loads((WORK/'voice'/(scene+'.json')).read_text())
        align=meta['alignment'];text=''.join(align['characters']).lower().replace('’',"'")
        index=text.find(phrase.lower().replace('’',"'"))
        if index<0:raise RuntimeError('Narration cue missing: '+phrase)
        target=align['character_start_times_seconds'][index]
        elapsed=time.monotonic()-self.start-self.marks['start']
        await self.wait(max(0,target-elapsed))

    async def wait(self, seconds=1): await self.p.wait_for_timeout(int(seconds*1000))

    async def go(self, path, testid=None):
        link=self.p.locator(f'a[href="{path}"]').first
        if await link.count() and await link.is_visible():
            await self.click(link)
        else:
            await self.p.goto(BASE+path,wait_until="domcontentloaded")
        await self.p.locator('main').wait_for(timeout=30000)
        if testid: await self.p.get_by_test_id(testid).wait_for(timeout=45000)
        await self.wait(1)
        if await self.p.get_by_test_id('cookie-refuse-btn').is_visible():
            await self.p.get_by_test_id('cookie-refuse-btn').click(force=True)
        await self.p.evaluate('document.fonts.ready')
        if path.startswith('/assistant'):
            search=self.p.locator('[data-testid^="assistant-history-search-"]:visible').first
            if await search.count(): await search.fill('appartement')

    async def click(self, locator):
        await locator.scroll_into_view_if_needed(timeout=15000)
        box=await locator.bounding_box()
        if not box: raise RuntimeError('Element has no visible click target')
        await self.p.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2,steps=24)
        await self.wait(.2); await locator.click(force=True); await self.wait(.55)

    async def optional(self, testid):
        el=self.p.get_by_test_id(testid)
        if await el.count() and await el.is_visible(): await self.click(el); return True
        return False

    async def wheel(self, dy=340):
        size=self.p.viewport_size
        await self.p.mouse.move(size['width']*.75,size['height']*.72,steps=20)
        await self.p.mouse.wheel(0,dy);await self.wait(1.2)

    async def type(self, locator, text):
        await self.click(locator);await locator.fill('');await locator.press_sequentially(text,delay=32);await self.wait(.5)

    async def tour(self, paths):
        for path in paths:
            await self.go(path);await self.wait(1.4);await self.wheel(180)

    async def settle(self, seconds):
        while seconds>0:
            await self.wait(min(2,seconds));seconds-=2