#!/usr/bin/env python3
"""Record the demo flow on the hosted app, then run ./rebuild.sh marks_live.json.
Usage: venv/bin/python record_live.py [--base URL] [--ask]
  --ask  ask Q041 live if the workspace has a model configured; otherwise falls back to the saved investigation.
Writes rec_live/*.webm and marks_live.json (mode: live | live_ask). No banner is added for live footage."""
import asyncio,time,json,sys,glob,os,shutil
from playwright.async_api import async_playwright
B=(sys.argv[sys.argv.index('--base')+1] if '--base' in sys.argv else 'https://sdlc-agent-five.vercel.app').rstrip('/')
ASK='--ask' in sys.argv
Q="Why did producers in 3.0 and 3.1 stay non-idempotent by default?"
INV='a[href*="non-idempotent"]'
HIDE_Q050="""(()=>{const p=document.querySelector('#proof'); if(!p) return 'no #proof';
 let hit=null; for(const el of p.querySelectorAll('*')){ if(el.children.length===0 && /26\\s*\\/\\s*27/.test(el.textContent)) {hit=el;break;} }
 if(!hit) return 'no 26/27 found';
 let card=hit; while(card.parentElement && card.parentElement!==p && card.textContent.length<120 && !/border/.test(card.className)) card=card.parentElement;
 if(!/border/.test(card.className)) card=hit.parentElement;
 for(const c of card.children) c.style.visibility='hidden'; return 'hidden: '+card.textContent.slice(0,60);})()"""
async def preflight(b):
    pg=await b.new_page(viewport={'width':1920,'height':1080})
    await pg.goto(B+'/w/kafka',wait_until='networkidle'); await pg.wait_for_timeout(2500)
    ok=await pg.locator(INV).count()>0
    model=False
    if ASK:
        await pg.goto(B+'/w/kafka/setup',wait_until='networkidle'); await pg.wait_for_timeout(2000)
        t=await pg.inner_text('body'); model=not ('Needs an API key' in t or 'not configured' in t)
    await pg.close(); return ok,model
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ok,model=await preflight(b)
        if not ok: print('ABORT: /w/kafka on',B,'has no saved idempotence investigation yet (workspace not live?). Nothing recorded.'); await b.close(); sys.exit(2)
        ask=ASK and model
        if ASK and not model: print('Model not configured on live workspace -> using saved investigation (narration keeps "saved investigations").')
        shutil.rmtree('rec_live',ignore_errors=True)
        ctx=await b.new_context(viewport={'width':1920,'height':1080},record_video_dir='rec_live',record_video_size={'width':1920,'height':1080})
        await ctx.add_init_script("try{localStorage.setItem('wb-theme','dark')}catch(e){}")
        pg=await ctx.new_page(); t0=time.time(); M={}
        def mark(n): M[n]=round(time.time()-t0,2); print(n,M[n],flush=True)
        await pg.goto(B+'/',wait_until='networkidle'); await pg.wait_for_timeout(1200)
        print(await pg.evaluate(HIDE_Q050)); mark('landing')
        await pg.mouse.move(900,500,steps=20); await pg.wait_for_timeout(3600)
        await pg.evaluate("document.querySelector('#proof').scrollIntoView({behavior:'smooth',block:'start'})")
        await pg.wait_for_timeout(1500); print(await pg.evaluate(HIDE_Q050)); mark('proof')
        await pg.mouse.move(700,500,steps=40); await pg.wait_for_timeout(6500); await pg.mouse.move(1100,560,steps=40); await pg.wait_for_timeout(7500)
        await pg.goto(B+'/workspaces',wait_until='networkidle'); await pg.locator('a[href="/w/kafka"]').first.wait_for(timeout=30000); await pg.wait_for_timeout(600); mark('ws')
        a=pg.locator('a[href="/w/kafka"]').first; bb=await a.bounding_box()
        await pg.mouse.move(bb['x']+bb['width']/2,bb['y']+bb['height']/2,steps=25); await pg.wait_for_timeout(3000)
        await a.click(); await pg.locator(INV).first.wait_for(timeout=30000); await pg.wait_for_timeout(600); mark('repo')
        if ask:
            box=pg.locator('textarea, input[placeholder*="Ask"]').last
            await box.click(); await box.type(Q,delay=35); await pg.wait_for_timeout(500); await box.press('Enter'); ts=time.time()
            M['repo_len']=round(time.time()-t0-M['repo']+1.0,2)
            await pg.get_by_text('supported').first.wait_for(timeout=600000); await pg.wait_for_timeout(800); mark('why')
            print('live answer took',round(time.time()-ts,1),'s')
        else:
            link=pg.locator(INV).first; await link.scroll_into_view_if_needed(); bb=await link.bounding_box()
            await pg.mouse.move(bb['x']+40,bb['y']+bb['height']/2,steps=30); await pg.wait_for_timeout(2400)
            await link.click(); await pg.get_by_text('supported').first.wait_for(timeout=30000); await pg.wait_for_timeout(800); mark('why')
        await pg.mouse.move(1650,150,steps=30); await pg.wait_for_timeout(5000)
        await pg.mouse.move(1650,450,steps=40); await pg.wait_for_timeout(5000)
        await pg.mouse.move(1650,880,steps=40); await pg.wait_for_timeout(4200)
        await pg.mouse.move(470,775,steps=20)
        await pg.get_by_text('Graph',exact=True).first.click(); mark('graph'); await pg.wait_for_timeout(2500)
        await pg.get_by_text('Trace',exact=False).last.click(); await pg.wait_for_timeout(500)
        await pg.mouse.move(1650,800,steps=30); await pg.mouse.wheel(0,600); await pg.wait_for_timeout(6000); mark('end')
        await ctx.close(); await b.close()
    M.update(webm=glob.glob('rec_live/*.webm')[0],mode='live_ask' if ask else 'live',banner=False,proof_off=-0.5)
    json.dump(M,open('marks_live.json','w'),indent=1); print('wrote marks_live.json; now run ./rebuild.sh marks_live.json')
asyncio.run(main())
