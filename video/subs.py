import re,subprocess
def dur(f): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f]))
def ts(x): return int(x)
def ass_t(x):
    h=int(x//3600);m=int(x%3600//60);s=x%60; return f"{h}:{m:02d}:{s:05.2f}"
def srt_t(x):
    ms=int(round(x*1000)); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
def p(t):
    h,m,r=t.split(':');s,ms=r.split(','); return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
off=0; ev=[]
for k in range(1,7):
    D=dur(f'aud/S{k}.mp3')+0.3
    blocks=open(f'aud/S{k}.srt').read().strip().split('\n\n')
    for b in blocks:
        L=b.split('\n'); a,c=[p(x.strip()) for x in L[1].split('-->')]; txt=' '.join(L[2:]).strip()
        words=txt.split(); chunks=[];cur=''
        for w in words:
            if len(cur)+len(w)+1>52 and cur: chunks.append(cur);cur=w
            else: cur=(cur+' '+w).strip()
        chunks.append(cur)
        tot=sum(len(x) for x in chunks); t=a
        for ch in chunks:
            d=(c-a)*len(ch)/tot; ev.append((off+t,off+t+d,ch)); t+=d
    off+=D
hdr="""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter,40,&H00F2ECE8,&H00FFFFFF,&H80100C0A,&H80100C0A,0,0,0,0,100,100,0,0,3,14,0,2,80,80,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
with open('out/engineering-memory.ass','w') as f:
    f.write(hdr)
    for a,b,t in ev: f.write(f"Dialogue: 0,{ass_t(a)},{ass_t(min(b,a+20)-0.02)},Default,,0,0,0,,{t}\n")
with open('out/engineering-memory.srt','w') as f:
    for i,(a,b,t) in enumerate(ev,1): f.write(f"{i}\n{srt_t(a)} --> {srt_t(b-0.02)}\n{t}\n\n")
print(len(ev),off)
