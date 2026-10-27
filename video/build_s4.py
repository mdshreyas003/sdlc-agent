# Build seg/S4.mp4 from a recording + marks json. Usage: python3 build_s4.py marks.json
import json,sys,subprocess
m=json.load(open(sys.argv[1]))
dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','aud/S4.mp3']))+0.3
H=3.62; P=13.85; WS=4.65; RP=m.get('repo_len',3.12)
po=m.get('proof_off',-1.34)
pieces=[(m['landing'],m['landing']+H),(m['proof']+po,m['proof']+po+P),(m['ws'],m['ws']+WS),(m['repo'],m['repo']+RP)]
used=sum(b-a for a,b in pieces); whylen=dur-used+0.5
pieces.append((m['why'],m['why']+whylen))
w0=used  # segment time at which the investigation view starts
z0,z1=w0+2.25,w0+10.0
Z=f"if(lt(t,{z0}),1,if(lt(t,{z0+1.5}),1+0.6*(t-{z0})/1.5,if(lt(t,{z1}),1.6,if(lt(t,{z1+1.5}),1.6-0.6*(t-{z1})/1.5,1))))".replace('t','(in/30)').replace('i(in/30)','it')
Z=Z.replace('l(in/30)','lt')
n=len(pieces)
fc=f"[0:v]fps=30,scale=1920:1080,split={n}"+''.join(f'[p{i}]' for i in range(n))+';'
fc+=''.join(f"[p{i}]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[q{i}];" for i,(a,b) in enumerate(pieces))
fc+=''.join(f'[q{i}]' for i in range(n))+f"concat=n={n}:v=1,trim=0:{dur:.3f},setpts=PTS-STARTPTS"
if m.get('mask'):
    x,y,w,h=m['mask']; fc+=f",drawbox=x={x}:y={y}:w={w}:h={h}:color=0x0A0A0A:t=fill:enable='between(t,{H-0.05},{H+P+0.05})'"
fc+=f",zoompan=z='{Z}':x='iw-iw/zoom':y='0':d=1:s=1920x1080:fps=30"
if m.get('banner'):
    fc+=",drawbox=x=(iw-760)/2:y=10:w=760:h=40:color=0x0A0C10@0.85:t=fill,drawtext=fontfile='/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf':text='Local build of the same app hosted at sdlc-agent-five.vercel.app':fontsize=22:fontcolor=0x6EA8FE:x=(w-tw)/2:y=20"
fc+='[v]'
subprocess.check_call(['ffmpeg','-y','-loglevel','error','-i',m['webm'],'-filter_complex',fc,'-map','[v]','-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p','-an','seg/S4.mp4'])
print('S4 built',round(dur,2),'s; investigation view from',round(w0,2))
