import json,sys,itertools
sys.path.insert(0,'/home/claude/blank-app/slab-scout/streamlit')
from core import grading
a=[x for f in ('part1.json','part2.json') for x in json.load(open(f)) if x[2]!='ERR']
y=[x[1] for x in a]
def g(x,use):
    co=x[4] if 'co' in use else 10; ed=x[5] if 'ed' in use else 10; su=x[6] if 'su' in use else 10
    cen=x[3] if 'cen' in use else 50
    r=grading.estimate(cen,None,co,ed,su,tcg=x[26] in ('pokemon','mtg','yugioh'))
    v=r['graders'][x[0]]['grade']; return float(str(v).split()[0])
for k in range(0,5):
  for use in itertools.combinations(['cen','co','ed','su'],k):
    p=[g(x,use) for x in a]; e=[abs(u-v) for u,v in zip(p,y)]
    print(use, round(sum(e)/len(e),2), 'exact',sum(v==0 for v in e),'w1',sum(v<=1 for v in e))
import collections; print(collections.Counter(y))
for x in a: print(x[0],x[1],'est',x[2],'cen',x[3],'sub',x[4:7],'chips',x[11],'scr/spk/stn',x[12:15],'wear',x[7],x[9],x[10],'px',x[18],x[19],'slab',x[23],x[25])
