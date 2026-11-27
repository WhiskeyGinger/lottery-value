"""Lottery value meter: what a Powerball or Mega Millions ticket is really worth, posted to Discord.

For each upcoming drawing:  value = sum over prize tiers of P(tier) x prize after tax
                                    + P(jackpot) x cash option after tax x expected share of the pot
* Odds are computed from each game's number matrix (they match the official charts exactly).
* Fixed prizes are the official base amounts. Mega Millions' built-in multiplier (2X-10X, odds from the
  official table) averages exactly 3X on non-jackpot prizes.
* Tax: federal 37% on the jackpot and on prizes over $5,000 (the withholding threshold); STATE_TAX is added.
  Prizes of $5,000 or less are treated as untaxed (most winners never pay on a few dollars).
* Splitting: other tickets also hit the jackpot. Ticket sales are ESTIMATED from the jackpot size (big jackpots
  sell many more tickets), and the expected share is E[1/(1+K)] with K ~ Poisson(tickets x jackpot odds).
Research and entertainment only. Nothing here buys tickets or suggests numbers.
"""
import datetime as dt, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from math import comb
from pathlib import Path

FEDERAL_TAX=0.37
TAX_THRESHOLD=5000
UA={'User-Agent':'lottery-value-meter/1.0 (Discord bot; github.com/WhiskeyGinger/lottery-value)','Accept':'application/json, text/html'}

def tier_odds(white_n, ball_n, whites, ball):
    pw=comb(5,whites)*comb(white_n-5,5-whites)/comb(white_n,5)
    return pw*((1/ball_n) if ball else (ball_n-1)/ball_n)

GAMES={
  'powerball':{'name':'Powerball','price':2.0,'white':69,'ball':26,'multiplier':1.0,'emoji':'🔴',
               'tiers':[((5,0),1_000_000),((4,1),50_000),((4,0),100),((3,1),100),((3,0),7),((2,1),7),((1,1),4),((0,1),4)],
               # Ticket-sales estimate (tickets per drawing) from the advertised jackpot: rough fit to published sales.
               'sales':(8_000_000,0.12)},
  'megamillions':{'name':'Mega Millions','price':5.0,'white':70,'ball':24,'multiplier':3.0,'emoji':'🟡',
               'tiers':[((5,0),1_000_000),((4,1),10_000),((4,0),500),((3,1),200),((3,0),10),((2,1),7),((1,1),7),((0,1),5)],
               'sales':(3_000_000,0.05)},
}
# Mega Millions built-in multiplier odds (official): 2X 15/32, 3X 10/32, 4X 4/32, 5X 2/32, 10X 1/32 -> mean exactly 3.0
MM_MULTIPLIER={2:15/32,3:10/32,4:4/32,5:2/32,10:1/32}
assert abs(sum(k*v for k,v in MM_MULTIPLIER.items())-3.0)<1e-12

def after_tax(amount, state_tax):
    return amount*(1-FEDERAL_TAX-state_tax) if amount>TAX_THRESHOLD else amount

def estimated_tickets(game, jackpot):
    base,slope=GAMES[game]['sales']; return base+slope*jackpot

def share_factor(tickets, p_jackpot):
    """Expected fraction of the jackpot you keep if you win, when others may also win (Poisson)."""
    lam=tickets*p_jackpot
    return 1.0 if lam<1e-9 else (1-math.exp(-lam))/lam

def ticket_value(game, jackpot, cash, state_tax=0.0, tickets=None):
    """Returns a dict with the ticket's expected value and its parts."""
    g=GAMES[game]; pj=tier_odds(g['white'],g['ball'],5,1)
    small=0.0
    for (w,b),prize in g['tiers']:
        p=tier_odds(g['white'],g['ball'],w,b)
        if game=='megamillions':
            small+=p*sum(prob*after_tax(prize*m,state_tax) for m,prob in MM_MULTIPLIER.items())
        else: small+=p*after_tax(prize,state_tax)
    tickets=tickets if tickets is not None else estimated_tickets(game,jackpot)
    share=share_factor(tickets,pj)
    jack=pj*after_tax(cash,state_tax)*share
    value=small+jack
    return {'game':game,'price':g['price'],'value':value,'small_prizes':small,'jackpot_part':jack,'jackpot':jackpot,'cash':cash,
            'after_tax_cash':after_tax(cash,state_tax),'share':share,'tickets_est':tickets,'jackpot_odds':1/pj,'state_tax':state_tax,
            'return_pct':value/g['price']}

def break_even_cash(game, state_tax=0.0):
    """Cash option at which the ticket would be worth its price (ignoring splitting): rough 'never' marker."""
    g=GAMES[game]; pj=tier_odds(g['white'],g['ball'],5,1); small=ticket_value(game,0,0,state_tax,tickets=0)['small_prizes']
    return (g['price']-small)/pj/(1-FEDERAL_TAX-state_tax)

# --- live jackpot data -------------------------------------------------------------------------------------------
def http(url, data=None, headers=None, opener=urllib.request.urlopen, attempts=3, sleep=time.sleep):
    h=dict(UA,**(headers or {}))
    for a in range(attempts):
        try:
            with opener(urllib.request.Request(url,data=data,headers=h,method='POST' if data is not None else 'GET'),timeout=30) as r:
                return r.read().decode('utf-8','replace')
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or a==attempts-1: raise
        except (urllib.error.URLError,TimeoutError):
            if a==attempts-1: raise
        sleep(2**(a+1))

def money(s):
    """'$850 Million' / '$1.2 Billion' / '850000000' -> dollars."""
    if s is None: return None
    if isinstance(s,(int,float)): return float(s)
    m=re.search(r'([\d,.]+)\s*(million|billion|m|b)?',str(s).replace('$',''),re.I)
    if not m: return None
    v=float(m.group(1).replace(',',''))
    unit=(m.group(2) or '').lower()
    return v*1e9 if unit in ('billion','b') else v*1e6 if unit in ('million','m') else v

POWERBALL_API='https://www.powerball.com/api/v1/estimates/powerball?_format=json'
MEGA_API='https://www.megamillions.com/cmspages/utilservice.asmx/GetLatestDrawData'

def powerball(fetch=http):
    """(jackpot, cash, next_draw_utc) from powerball.com."""
    d=json.loads(fetch(POWERBALL_API))
    row=d[0] if isinstance(d,list) and d else d
    jackpot=money(row.get('field_prize_amount')); cash=money(row.get('field_prize_amount_cash'))
    when=row.get('field_next_draw_date')
    return jackpot,cash,parse_when(when)

def megamillions(fetch=http):
    raw=fetch(MEGA_API,data=b'{}',headers={'Content-Type':'application/json; charset=utf-8'})
    d=json.loads(raw); d=json.loads(d['d']) if isinstance(d.get('d'),str) else d
    j=d.get('Jackpot') or {}
    return money(j.get('NextPrizePool')),money(j.get('NextCashValue')),parse_when(d.get('NextDrawingDate'))

def parse_when(s):
    if not s: return None
    s=str(s).strip()
    for f in (lambda x: dt.datetime.fromisoformat(x.replace('Z','+00:00')),):
        try:
            d=f(s); return d if d.tzinfo else d.replace(tzinfo=EASTERN_GUESS(d))
        except ValueError: pass
    return None

def EASTERN_GUESS(d):
    """Draw times are published in Eastern time without an offset: EST/EDT by the US rule."""
    return dt.timezone(dt.timedelta(hours=-4 if is_dst_us(d) else -5))

def is_dst_us(d):
    y=d.year
    def nth_sunday(month,n):
        x=dt.date(y,month,1); x+=dt.timedelta(days=(6-x.weekday())%7); return x+dt.timedelta(weeks=n-1)
    return nth_sunday(3,2)<=d.date()<nth_sunday(11,1)

def central(t):
    t=t.astimezone(dt.timezone.utc); dst=is_dst_us(t-dt.timedelta(hours=6)); local=t+dt.timedelta(hours=-5 if dst else -6)
    return local.strftime('%a %b ')+str(local.day)+local.strftime(', %I:%M %p ').replace(' 0',' ')+('CDT' if dst else 'CST')

def big(x):
    return ('$%.2fB'%(x/1e9)).replace('.00B','B') if x>=1e9 else '$%.0fM'%(x/1e6)

# --- Discord -----------------------------------------------------------------------------------------------------
def embed(r, when, state_label):
    g=GAMES[r['game']]; worth=r['value']; price=r['price']; good=worth>price
    head='%s %s — %s jackpot'%(g['emoji'],g['name'],big(r['jackpot']))+(' · %s'%central(when) if when else '')
    lines=['💵 A $%g ticket is really worth **$%.2f**'%(price,worth)]
    if good: lines.append('🚨 **Worth more than it costs** — about **+$%.2f** per ticket on average'%(worth-price))
    else: lines.append('📉 You lose about **$%.2f** per ticket on average (you get back %d%%)'%(price-worth,round(100*worth/price)))
    lines.append('_Why: %s cash option → %s after taxes → you keep about %d%% if you win (bigger jackpots sell more tickets, so more people split it)_'%(
        big(r['cash']),big(r['after_tax_cash']),round(100*r['share'])))
    return {'title':head,'description':'\n'.join(lines),'color':15548997 if good else 15105570,
            'footer':{'text':'Odds 1 in %s · taxes: 37%% federal%s · ticket sales estimated · not betting advice'%('{:,}'.format(round(r['jackpot_odds'])),state_label)}}

def message(results):
    any_good=any(r['value']>r['price'] for r,_ in results)
    m={'username':'Lottery Value Meter','allowed_mentions':{'parse':[]},'embeds':[embed(r,w,STATE_LABEL) for r,w in results]}
    if any_good: m['content']='🚨 **Rare: a lottery ticket is worth more than it costs today.**'
    return m

STATE_TAX=float(os.environ.get('STATE_TAX','0') or 0)
STATE_NAME=os.environ.get('STATE_NAME','').strip()
STATE_LABEL=(' + %s %.2g%%'%(STATE_NAME or 'state',STATE_TAX*100)) if STATE_TAX else ', state tax not included'

# --- run ---------------------------------------------------------------------------------------------------------
STATE_PATH=Path(os.environ.get('STATE_PATH','.state/posted.json'))
FETCHERS={'powerball':powerball,'megamillions':megamillions}
MIN_JACKPOT=float(os.environ.get('MIN_JACKPOT','0') or 0)

def central_date(t):
    t=t.astimezone(dt.timezone.utc); return (t+dt.timedelta(hours=-5 if is_dst_us(t-dt.timedelta(hours=6)) else -6)).date()

def deliver(hook, payload, opener=urllib.request.urlopen, sleep=time.sleep, attempts=3):
    url=hook+('&' if '?' in hook else '?')+'wait=true'
    for a in range(attempts):
        try:
            req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':UA['User-Agent']},method='POST')
            with opener(req,timeout=30) as r: return 200<=r.status<300
        except urllib.error.HTTPError as e:
            if e.code==429: sleep(2); continue
            if e.code<500: return False
        except (urllib.error.URLError,TimeoutError): pass
        if a<attempts-1: sleep(2**(a+1))
    return False

def run(hook, now=None, fetchers=None, send=deliver, state_path=STATE_PATH, state_tax=None):
    """Post each game whose next drawing is today (Central), once per drawing."""
    now=now or dt.datetime.now(dt.timezone.utc); fetchers=fetchers or FETCHERS; state_tax=STATE_TAX if state_tax is None else state_tax
    try: posted=json.loads(Path(state_path).read_text())
    except (OSError,ValueError): posted={}
    rep={'checked':[],'posted':[],'errors':[]}; due=[]
    for game,fetch in fetchers.items():
        try: jackpot,cash,when=fetch()
        except Exception as e: rep['errors'].append('%s: %s'%(game,type(e).__name__)); continue
        rep['checked'].append({'game':game,'jackpot':jackpot,'cash':cash,'draw':when.isoformat() if when else None})
        if not jackpot or not cash or not when: rep['errors'].append('%s: incomplete data'%game); continue
        if central_date(when)!=central_date(now) or when<now: continue
        if jackpot<MIN_JACKPOT: continue
        k='%s|%s'%(game,when.date().isoformat())
        if k in posted: continue
        due.append((k,ticket_value(game,jackpot,cash,state_tax),when))
    if due and send(hook,message([(r,w) for _,r,w in due])):
        for k,_,_ in due: posted[k]=now.isoformat(); rep['posted'].append(k)
    Path(state_path).parent.mkdir(parents=True,exist_ok=True); Path(state_path).write_text(json.dumps(posted,indent=1,sort_keys=True))
    return rep

def sample(now):
    r1=ticket_value('powerball',850e6,400e6,STATE_TAX); r2=ticket_value('megamillions',1.5e9,690e6,STATE_TAX)
    m=message([(r1,now+dt.timedelta(hours=10)),(r2,now+dt.timedelta(hours=34))])
    for e in m['embeds']: e['title']='🧪 SAMPLE — '+e['title']
    m['content']='🧪 **Sample with made-up jackpots** — this is what real posts look like.'
    return m

def main():
    hook=os.environ.get('DISCORD_WEBHOOK_URL')
    if not hook: sys.exit('DISCORD_WEBHOOK_URL is not set (Settings → Secrets and variables → Actions)')
    mode=os.environ.get('MODE','run')
    if mode=='sample': ok=deliver(hook,sample(dt.datetime.now(dt.timezone.utc))); print('sample delivered' if ok else 'sample failed'); sys.exit(0 if ok else 1)
    if mode=='probe':
        for game,f in FETCHERS.items():
            try: print(game,f())
            except Exception as e: print(game,'ERROR',type(e).__name__,str(e)[:300])
        return
    rep=run(hook); print(json.dumps(rep))
    if len(rep['errors'])==len(FETCHERS): sys.exit('No jackpot data could be read: '+'; '.join(rep['errors']))
if __name__=='__main__': main()
