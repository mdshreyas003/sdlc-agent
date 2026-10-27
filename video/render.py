import sys,subprocess,math
from PIL import Image,ImageDraw,ImageFont
W,H,FPS=1920,1080,30
BG=(10,12,16);FG=(232,236,242);DIM=(138,147,163);AC=(110,168,254);LINE=(44,50,62);CARD=(20,24,31)
FV='/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf'
MONO='/usr/share/fonts/truetype/sand-box/google/JetBrains Mono/'
import glob
MONOF=sorted(glob.glob(MONO+'*.ttf'))[0]
_fc={}
def F(sz,w=500,mono=False):
    k=(sz,w,mono)
    if k not in _fc:
        if mono: f=ImageFont.truetype(MONOF,sz)
        else:
            f=ImageFont.truetype(FV,sz)
            try: f.set_variation_by_axes([min(32,max(14,sz)),w])
            except Exception:
                try: f.set_variation_by_axes([w])
                except Exception: pass
        _fc[k]=f
    return _fc[k]
def ease(x): x=max(0,min(1,x)); return 1-(1-x)**3
def A(c,a): return c+(int(255*a),)
class S:
    def __init__(s,dur): s.items=[];s.dur=dur
    def text(s,t,x,y,txt,sz=48,w=500,col=FG,anchor='la',mono=False): s.items.append((t,'text',dict(x=x,y=y,txt=txt,sz=sz,w=w,col=col,anchor=anchor,mono=mono)))
    def box(s,t,x,y,bw,bh,fill=CARD,outline=LINE,dashed=False,r=18,width=2): s.items.append((t,'box',dict(x=x,y=y,w=bw,h=bh,fill=fill,outline=outline,dashed=dashed,r=r,width=width)))
    def line(s,t,x1,y1,x2,y2,col=LINE,width=3,arrow=False,dashed=False): s.items.append((t,'line',dict(x1=x1,y1=y1,x2=x2,y2=y2,col=col,width=width,arrow=arrow,dashed=dashed)))
    def dot(s,t,x,y,r=10,col=AC): s.items.append((t,'dot',dict(x=x,y=y,r=r,col=col)))
    def func(s,t,fn): s.items.append((t,'fn',dict(fn=fn)))
def dashed_rect(d,x,y,w,h,col,width=2,seg=14):
    for (a,b,c,e) in [(x,y,x+w,y),(x,y+h,x+w,y+h),(x,y,x,y+h),(x+w,y,x+w,y+h)]:
        L=math.hypot(c-a,e-b);n=int(L//(seg*2))+1
        for i in range(n):
            t0=i*2*seg/L;t1=min(1,(i*2+1)*seg/L)
            d.line([(a+(c-a)*t0,b+(e-b)*t0),(a+(c-a)*t1,b+(e-b)*t1)],fill=col,width=width)
def draw(scene,t):
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im,'RGBA')
    for (t0,k,p) in scene.items:
        a=ease((t-t0)/0.55)
        if a<=0: continue
        dy=(1-a)*22
        if k=='text':
            d.text((p['x'],p['y']+dy),p['txt'],font=F(p['sz'],p['w'],p['mono']),fill=A(p['col'],a),anchor=p['anchor'])
        elif k=='box':
            x,y,w,h=p['x'],p['y']+dy,p['w'],p['h']
            if p['dashed']:
                d.rounded_rectangle([x,y,x+w,y+h],p['r'],fill=A(p['fill'],a)); dashed_rect(d,x,y,w,h,A(p['outline'],a),p['width'])
            else: d.rounded_rectangle([x,y,x+w,y+h],p['r'],fill=A(p['fill'],a),outline=A(p['outline'],a),width=p['width'])
        elif k=='line':
            x1,y1,x2,y2=p['x1'],p['y1'],p['x2'],p['y2']
            xe=x1+(x2-x1)*a; ye=y1+(y2-y1)*a
            if p['dashed']:
                L=math.hypot(xe-x1,ye-y1);n=int(L//20)+1
                for i in range(n):
                    f0=i*20/max(L,1);f1=min(1,(i*20+10)/max(L,1))
                    d.line([(x1+(xe-x1)*f0,y1+(ye-y1)*f0),(x1+(xe-x1)*f1,y1+(ye-y1)*f1)],fill=A(p['col'],1),width=p['width'])
            else: d.line([(x1,y1),(xe,ye)],fill=A(p['col'],1),width=p['width'])
            if p['arrow'] and a>0.95:
                ang=math.atan2(y2-y1,x2-x1);s=14
                d.polygon([(x2,y2),(x2-s*math.cos(ang-0.45),y2-s*math.sin(ang-0.45)),(x2-s*math.cos(ang+0.45),y2-s*math.sin(ang+0.45))],fill=A(p['col'],1))
        elif k=='dot':
            r=p['r']*a; d.ellipse([p['x']-r,p['y']+dy-r,p['x']+r,p['y']+dy+r],fill=A(p['col'],a))
        elif k=='fn': p['fn'](d,t-t0,a)
    return im
def chip(s,t,x,y,label,col=FG,sz=34,pad=26,fill=CARD,outline=LINE,dashed=False,anchor_center=True,w=None):
    tw=F(sz,500).getlength(label); bw=w or tw+pad*2; bh=sz+pad*1.4
    bx=x-bw/2 if anchor_center else x
    s.box(t,bx,y,bw,bh,fill=fill,outline=outline,dashed=dashed,r=bh/2 if not w else 16)
    s.text(t,bx+bw/2,y+bh/2,label,sz=sz,col=col,anchor='mm')
    return bx,bw,bh
def tag(s,t,x,y,label,col=AC):
    s.text(t,x,y,label.upper(),sz=24,w=650,col=col)

def S1(dur):
    s=S(dur)
    s.text(0.1,W/2,300,'Engineering Memory',sz=96,w=700,anchor='mm')
    s.text(0.6,W/2,390,'answers to “why is this code like this?”',sz=40,col=DIM,anchor='mm')
    src=['Mailing lists','Jira tickets','Pull requests','Commits','Design docs']
    pos=[(420,500),(860,470),(1300,510),(640,610),(1100,620)]
    for i,(l,(x,y)) in enumerate(zip(src,pos)): chip(s,3.8+i*1.4,x,y,l)
    s.text(12.6,W/2,745,'“Why was this decided?”  →  hours of digging',sz=46,w=600,col=AC,anchor='mm')
    def fade_title(d,tt,a):
        pass
    users=['Engineers','Forward-deployed engineers','New hires','Tech leads']
    # second phase: users replace bottom line area
    s.items_phase2=True
    x=W/2-0; y=910
    s2=[]
    xs=[330,780,1250,1620]
    for i,(u,xx) in enumerate(zip(users,xs)): s.text(19.0+i*1.6,xx,y-10,u,sz=34,col=FG,anchor='mm')
    s.line(18.6,200,y-50,W-200,y-50,col=LINE,width=2)
    tag(s,18.6,200,y-95,'Who it helps',col=DIM)
    return s
def S2(dur):
    s=S(dur)
    tag(s,0.1,160,120,'What it does')
    s.text(0.1,160,165,'Answers “why” questions from your team’s own history',sz=52,w=650)
    # pillar 1 graph
    s.box(4.9,160,300,760,440)
    s.text(4.9,200,330,'1  Explicit links only',sz=40,w=650)
    nodes=[(260,520,'Mail'),(520,440,'Jira'),(520,620,'PR'),(780,620,'Commit')]
    edges=[(0,1,'REFERENCES'),(0,1,None),(2,1,'REFERENCES'),(2,3,'CONTAINS')]
    s.line(7,260,520,520,440,col=AC,width=3);s.text(7.3,330,455,'REFERENCES',sz=20,col=DIM,mono=True)
    s.line(9,520,620,520,440,col=AC,width=3);s.text(9.3,540,520,'REFERENCES',sz=20,col=DIM,mono=True)
    s.line(11,520,620,780,620,col=AC,width=3);s.text(11.3,590,640,'CONTAINS',sz=20,col=DIM,mono=True)
    s.text(6,260,600,'REPLIES_TO ↺',sz=20,col=DIM,mono=True,anchor='mm')
    for i,(x,y,l) in enumerate(nodes):
        s.dot(5.5+i*0.3,x,y,16,AC); s.text(5.5+i*0.3,x,y-40,l,sz=28,anchor='mm')
    s.text(15.9,200,690,'Never guessed from similar words or timing',sz=28,col=DIM)
    # pillar 2
    s.box(18.5,1000,300,760,440)
    s.text(18.5,1040,330,'2  Quotes checked in code',sz=40,w=650)
    s.box(19.5,1040,410,680,120,fill=(14,17,23))
    s.text(19.6,1070,440,'“Fixes PAY-412”',sz=34,col=FG,mono=True)
    s.text(19.9,1070,490,'✓ verbatim in source text',sz=26,col=AC)
    s.box(25.1,1040,570,680,120,fill=(14,17,23),outline=AC)
    s.text(25.2,1070,600,'No proof?',sz=30,col=DIM)
    s.text(25.4,1070,640,'“Not established”',sz=36,w=650,col=AC)
    # memory designed
    s.box(29.6,160,780,1600,110,fill=(14,16,20),outline=DIM,dashed=True)
    s.text(29.7,200,835,'Memory layer: facts formed from evidence, kept current, tied to sources',sz=34,col=FG,anchor='lm')
    chip(s,37.0,1640,805,'DESIGNED · NEXT',col=DIM,sz=24,pad=18,fill=(14,16,20),outline=DIM)
    return s
def S3(dur):
    s=S(dur)
    tag(s,0.1,160,110,'Architecture')
    s.text(0.1,160,150,'How it fits together',sz=56,w=650)
    L=[('Sources','GitHub · Jira · chat',2.5),('Ingest & linking','one node per item',6.5),('Neo4j graph','explicit links',9.5),('LangGraph agent','read-only tools',13.2),('FastAPI','HTTP API',33.2),('Next.js','workbench',35.0)]
    bw,gap=250,46; x0=(W-(6*bw+5*gap))/2; y=290
    cx=[]
    for i,(a,b,t) in enumerate(L):
        x=x0+i*(bw+gap); cx.append(x)
        s.box(t,x,y,bw,130,outline=AC if i==3 else LINE)
        s.text(t,x+bw/2,y+48,a,sz=30,w=650,anchor='mm'); s.text(t,x+bw/2,y+92,b,sz=22,col=DIM,anchor='mm')
        if i>0: s.line(t-0.2,x-gap+4,y+65,x-6,y+65,col=AC,width=3,arrow=True)
    # memory designed under graph
    mx=cx[2]; s.box(29.0,mx-30,y+170,bw+60,90,fill=(14,16,20),outline=DIM,dashed=True)
    s.text(29.0,mx+bw/2,y+200,'Memory layer',sz=26,anchor='mm'); s.text(29.0,mx+bw/2,y+235,'designed · not built',sz=20,col=DIM,anchor='mm')
    s.line(29.0,mx+bw/2,y+130,mx+bw/2,y+170,col=DIM,width=2,dashed=True)
    steps=['understand','seed IDs','plan','retrieve','evaluate','synthesize','verify']
    sy=640; sw=200; sg=28; sx0=(W-(7*sw+6*sg))/2
    tag(s,13.2,sx0,sy-70,'Agent steps',col=DIM)
    for i,st in enumerate(steps):
        x=sx0+i*(sw+sg); t=13.6+i*1.4
        s.box(t,x,sy,sw,70,r=35)
        s.text(t,x+sw/2,sy+35,st,sz=26,anchor='mm',col=AC if st=='verify' else FG)
        if i: s.line(t-0.1,x-sg+3,sy+35,x-3,sy+35,col=LINE,width=2)
    def pulse(d,tt,a):
        tot=7*(sw+sg); p=(tt*260)%tot; x=sx0+p
        d.ellipse([x-7,sy-18-7,x+7,sy-18+7],fill=A(AC,a))
    s.func(23.5,pulse)
    g=['read-only tools','ID guard','quote verifier']
    for i,gg in enumerate(g): chip(s,24.6+i*2.6,W/2+(i-1)*420,770,'✓ '+gg,sz=30)
    s.text(38.3,W/2,890,'Any OpenAI-compatible model  ·  running Sarvam',sz=32,col=DIM,anchor='mm')
    return s
def S5(dur):
    s=S(dur)
    tag(s,0.1,160,110,'Results so far')
    chip(s,0.1,W-160-260,95,'PRELIMINARY',col=AC,sz=26,pad=20,outline=AC,anchor_center=False,w=260)
    s.text(0.6,160,150,'Gold set not yet human-verified (0 / 75). No accuracy numbers.',sz=36,col=DIM)
    cards=[('1,191','artifacts','eval corpus · Kafka only',3.5),('1,786','explicit links','eval corpus',6.0),('10','Kafka KIPs','eval corpus',9.5),('75','gold questions','with traps · 0 human-verified',14.7)]
    cw,cg=380,40;x0=(W-(4*cw+3*cg))/2
    for i,(n,l,sub,t) in enumerate(cards):
        x=x0+i*(cw+cg); s.box(t,x,240,cw,230)
        s.text(t,x+36,270,n,sz=84,w=700,col=AC); s.text(t,x+36,380,l,sz=32); s.text(t,x+36,425,sub,sz=22,col=DIM)
    cards2=[('5 / 7','real-model e2e gate passed','unmerged branch',22.9),('1 → 9 / 18','dev questions fully reachable','raw proxy · 0 regressions',29.8),('Q006','correctly “Not established”','no answer in the data',38.2),('445 / 7','tests passed / skipped','unmerged branch',43.9)]
    for i,(n,l,sub,t) in enumerate(cards2):
        x=x0+i*(cw+cg); s.box(t,x,510,cw,230)
        s.text(t,x+36,540,n,sz=72 if len(n)<8 else 60,w=700,col=FG); s.text(t,x+36,640,l,sz=27); s.text(t,x+36,685,sub,sz=20,col=DIM)
    return s
def S6(dur):
    s=S(dur)
    tag(s,0.1,160,110,'Deliberate choices')
    ch=[('Explicit links over guesses',2.6),('Abstaining is a real answer',8.0),('Licence-safe data fetch',10.8),('Idempotent migrations',13.0)]
    for i,(c,t) in enumerate(ch): s.text(t,160,170+i*70,'—  '+c,sz=40,w=550)
    tag(s,15.8,1080,110,'Next',col=AC)
    nx=[('Memory layer','designed (ADR-003)'),('75-question benchmark vs baselines','planned'),('More sources','planned')]
    for i,(a,b) in enumerate(nx):
        t=15.8+i*2.3; s.box(t,1080,165+i*120,680,96,fill=(14,16,20),outline=DIM,dashed=True)
        s.text(t,1110,195+i*120,a,sz=32,w=600); s.text(t,1110,235+i*120,b,sz=22,col=DIM)
    def clear(d,tt,a): d.rectangle([0,0,W,H],fill=A(BG,a))
    s.func(24.1,clear)
    s.text(24.4,W/2,400,'Engineering Memory',sz=96,w=700,anchor='mm')
    s.text(25.0,W/2,500,'Answers you can check, or an honest “Not established.”',sz=40,col=AC,anchor='mm')
    s.text(26.0,W/2,640,'github.com/mdshreyas003/sdlc-agent',sz=30,col=DIM,anchor='mm',mono=True)
    s.text(26.2,W/2,690,'sdlc-agent-five.vercel.app',sz=30,col=DIM,anchor='mm',mono=True)
    return s
k=sys.argv[1]; dur=float(sys.argv[2]); scene=globals()[k](dur)
out=f'seg/{k}.mp4'
p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p',out],stdin=subprocess.PIPE)
n=int(dur*FPS); last=None; lastkey=None
for i in range(n):
    t=i/FPS
    im=draw(scene,t); p.stdin.write(im.tobytes())
p.stdin.close(); p.wait(); print('done',k)
