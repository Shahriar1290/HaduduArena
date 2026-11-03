import random, copy, time, sys
R, C = 6, 8
START = {0: [(0,2),(1,3),(3,1),(4,3),(5,2)]}
START[1] = [(r, 7-c) for r, c in START[0]]
HOME = {0: range(0,4), 1: range(4,8)}
NB = [(dr,dc) for dr in (-1,0,1) for dc in (-1,0,1) if (dr,dc)!=(0,0)]
BREATH = 6
DOD = 2
RESET_BOTH = True
RAIDS = 16

def new():
    return dict(pos={0:list(START[0]),1:list(START[1])}, outq={0:[],1:[]}, score=[0,0], raid=0,
                phase='pick', rd=None, breath=0, crossed=False, tagged=set(), over=False, empty=[0,0], dod=False)

def attacker(s): return (s['raid'] + s.get('first',0)) % 2
def player(s):
    a = attacker(s)
    return a if s['phase'] in ('pick','raider') else 1-a

def occupied(s):
    return {p for t in (0,1) for p in s['pos'][t] if p is not None}

def adj_def(s, cell):
    d = 1-attacker(s)
    return [i for i,p in enumerate(s['pos'][d]) if p is not None and max(abs(p[0]-cell[0]),abs(p[1]-cell[1]))==1]

def actions(s):
    a = attacker(s); d = 1-a
    if s['phase']=='pick':
        return [('raid',i) for i,p in enumerate(s['pos'][a]) if p is not None]
    occ = occupied(s)
    if s['phase']=='raider':
        r,c = s['pos'][a][s['rd']]
        acts = []
        for dr,dc in NB:
            n=(r+dr,c+dc)
            if 0<=n[0]<R and 0<=n[1]<C and n not in occ: acts.append(('step',n))
        if c not in HOME[a]:   # in defenders' half
            if any(i not in s['tagged'] for i in adj_def(s,(r,c))): acts.append(('touch',))
        elif not s['crossed'] and not s['dod']:
            acts.append(('stop',))
        return acts
    # defender
    acts=[('hold',)]
    for i,p in enumerate(s['pos'][d]):
        if p is None: continue
        for dr,dc in NB:
            n=(p[0]+dr,p[1]+dc)
            if 0<=n[0]<R and n[1] in HOME[d] and 0<=n[0]<R and n not in occ: acts.append(('move',i,n))
    return acts

def revive(s, t, k):
    for _ in range(k):
        if not s['outq'][t]: break
        i = s['outq'][t].pop(0)
        occ = occupied(s)
        cell = START[t][i]
        if cell in occ:
            cands=[(r,c) for r in range(R) for c in HOME[t] if (r,c) not in occ]
            cell = min(cands, key=lambda x:(abs(x[0]-cell[0])+abs(x[1]-cell[1]),x))
        s['pos'][t][i]=cell

def check_allout(s):
    for t in (0,1):
        if all(p is None for p in s['pos'][t]):
            s['score'][1-t]+=2
            s['outq'][t]=[]
            s['pos'][t]=list(START[t])
            occ = occupied(s)

def empty_raid(s):
    a=attacker(s); d=1-a
    s['empty'][a]+=1
    if s['dod']:
        i=s['rd']; s['pos'][a][i]=None; s['outq'][a].append(i)
        s['score'][d]+=1; s['empty']=[0,0]
        revive(s,d,1); check_allout(s)
    end_raid(s)

def end_raid(s):
    s['dod']=False
    s['raid']+=1; s['phase']='pick'; s['rd']=None; s['tagged']=set(); s['crossed']=False
    if s['raid']>=RAIDS: s['over']=True

def caught(s):
    a=attacker(s); d=1-a
    i=s['rd']; s['pos'][a][i]=None; s['outq'][a].append(i)
    s['tagged']=set(); s['score'][d]+=1; s['empty']=[0,0] if RESET_BOTH else [s['empty'][0]*(a==1), s['empty'][1]*(a==0)]
    revive(s,d,1)
    check_allout(s); end_raid(s)

def success(s):
    a=attacker(s); d=1-a
    k=len(s['tagged'])
    if k==0:
        empty_raid(s); return
    s['empty']=[0,0] if RESET_BOTH else [s['empty'][0]*(a==1), s['empty'][1]*(a==0)]
    for i in sorted(s['tagged']):
        s['pos'][d][i]=None; s['outq'][d].append(i)
    s['score'][a]+=k
    revive(s,a,k)
    check_allout(s); end_raid(s)

def tackle_check(s):
    a=attacker(s)
    r,c=s['pos'][a][s['rd']]
    return c not in HOME[a] and len(adj_def(s,(r,c)))>=3

def result(s, act):
    s=copy.deepcopy(s); a=attacker(s)
    ph=s['phase']
    if ph=='pick':
        s['rd']=act[1]; s['dod']=s['empty'][a]>=DOD; s['breath']=BREATH; s['crossed']=False; s['tagged']=set(); s['phase']='raider'
        if not actions(s): caught(s)
        return s
    if ph=='raider':
        if act[0]=='stop':
            empty_raid(s); return s
        s['breath']-=1
        if act[0]=='step':
            s['pos'][a][s['rd']]=act[1]
            if act[1][1] not in HOME[a]: s['crossed']=True
            elif s['crossed']:
                success(s); return s
        else:
            r,c=s['pos'][a][s['rd']]
            s['tagged']|={i for i in adj_def(s,(r,c))}
        if s['breath']==0:
            c=s['pos'][a][s['rd']][1]
            if c not in HOME[a]: caught(s)
            else: empty_raid(s)
            return s
        if tackle_check(s): caught(s); return s
        s['phase']='defender'; return s
    # defender
    if act[0]=='move':
        s['pos'][1-a][act[1]]=act[2]
    if tackle_check(s): caught(s); return s
    s['phase']='raider'
    if not actions(s): caught(s)
    return s

def terminal(s): return s['over']
def utility(s): return s['score'][0]-s['score'][1]

def random_game(rng):
    s=new(); n=0
    while not terminal(s):
        s=result(s, rng.choice(actions(s))); n+=1
        if n>5000: return None
    return s,n

if __name__=='__main__':
    rng=random.Random(1)
    s=new()
    print('pick actions',len(actions(s)))
    s2=result(s,('raid',1)); print('raider actions',len(actions(s2)))
    s3=result(s2,actions(s2)[0]); print('defender actions',len(actions(s3)))
    w=[0,0,0]; tot=0; sc=[0,0]; mx=0
    for g in range(3000):
        r=random_game(rng)
        if r is None: print('LOOP'); break
        st,n=r; tot+=n; mx=max(mx,n); sc[0]+=st['score'][0]; sc[1]+=st['score'][1]
        u=utility(st); w[0 if u>0 else 1 if u<0 else 2]+=1
    print('random wins A/B/draw',w,'avg plies',tot/3000,'max',mx,'avg score',sc[0]/3000,sc[1]/3000)
