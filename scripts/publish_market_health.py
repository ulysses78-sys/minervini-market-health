"""Validate and publish only aggregate Market Health snapshots. Never overwrite."""
import base64
import hashlib
import re
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import exchange_calendars as xcals

REPOSITORY='ulysses78-sys/minervini-market-health'
BRANCH='main'
COLUMNS='date,collected_at,regime,score,coverage_pct,breadth50,breadth200,leadership_health,breakout_success_rate,breakout_event_count,distribution_count,warning_flags,price_source,universe_source,universe_version,universe_total,universe_covered,breadth_eligible,leadership_eligible,trend_score,breadth_score,leadership_score,breakout_score,pressure_score,engine_version,date_convention'.split(',')
WEIGHTS={'trend_score':25,'breadth_score':20,'leadership_score':20,'breakout_score':20,'pressure_score':15}

def sanitized_csv(frame):
    if frame.empty or len(frame)>3000 or set(frame.columns)!=set(COLUMNS):
        raise ValueError('Agregado vazio, excessivo ou com colunas inesperadas; publicação bloqueada.')
    d=frame[COLUMNS].copy()
    dates=pd.to_datetime(d.date,format='%Y-%m-%d',errors='raise')
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError('Datas duplicadas ou fora de ordem.')
    sessions=xcals.get_calendar('XNYS').sessions_in_range(dates.min(),dates.max())
    if sessions.tz is not None: sessions=sessions.tz_localize(None)
    if not pd.DatetimeIndex(dates).equals(sessions):
        raise ValueError('Datas não correspondem ao calendário XNYS completo.')
    collected=pd.to_datetime(d.collected_at,utc=True,errors='raise')
    if collected.isna().any() or (collected.dt.tz_localize(None).dt.normalize()<dates).any():
        raise ValueError('Data da coleta inválida.')
    if (collected>pd.Timestamp.now(tz='UTC')+pd.Timedelta(minutes=5)).any():
        raise ValueError('Coleta no futuro.')
    d['date']=dates.dt.strftime('%Y-%m-%d')
    d['collected_at']=collected.map(lambda v:v.isoformat())
    approved={'price_source':{'yfinance'},'universe_source':{'github_datasets','wikipedia','cache_local_potencialmente_desatualizado'},'engine_version':{'0.3.1','0.3.2'},'date_convention':{'exchange_session_date'},'regime':{'FAVORAVEL','NEUTRO','DEFENSIVO','NO_DATA'}}
    for col,values in approved.items():
        if not d[col].isin(values).all(): raise ValueError('Metadados não reconhecidos: '+col)
    if not d.universe_version.astype(str).str.fullmatch(r'current_sp500_[0-9]{3}_survivorship_bias').all():
        raise ValueError('Família metodológica não reconhecida.')
    valid_flags={'INSUFFICIENT_COVERAGE','BREADTH_WEAK','BREAKOUTS_WEAK'}
    for value in d.warning_flags.fillna(''):
        if not isinstance(value,str) or (value and not set(value.split('|')).issubset(valid_flags)):
            raise ValueError('Alertas não reconhecidos.')
    d['warning_flags']=d.warning_flags.fillna('')
    numeric=['score','coverage_pct','breadth50','breadth200','leadership_health','breakout_success_rate','breakout_event_count','distribution_count','universe_total','universe_covered','breadth_eligible','leadership_eligible',*WEIGHTS]
    for col in numeric:
        d[col]=pd.to_numeric(d[col],errors='raise')
        if np.isinf(d[col]).any(): raise ValueError('Valor infinito: '+col)
    for col in ['breadth50','breadth200','leadership_health','breakout_success_rate']:
        if not (d[col].isna()|d[col].between(0,1)).all(): raise ValueError('Proporção fora dos limites.')
    for col,maximum in WEIGHTS.items():
        if not (d[col].isna()|d[col].between(0,maximum)).all(): raise ValueError('Componente fora dos limites.')
    calculated=sum(d[col].notna().astype(int)*maximum for col,maximum in WEIGHTS.items())
    if not d.coverage_pct.eq(calculated).all(): raise ValueError('Cobertura dos componentes inconsistente.')
    complete=d.coverage_pct.eq(100)
    if not d.loc[complete,'score'].between(0,100).all() or not d.loc[~complete,'score'].isna().all():
        raise ValueError('Score inconsistente com NO_DATA.')
    if not np.allclose(d.loc[complete,list(WEIGHTS)].sum(axis=1),d.loc[complete,'score']):
        raise ValueError('Soma dos componentes inconsistente.')
    expected=d.score.map(lambda s:'NO_DATA' if pd.isna(s) else 'FAVORAVEL' if s>=70 else 'NEUTRO' if s>=45 else 'DEFENSIVO')
    if not d.regime.eq(expected).all(): raise ValueError('Regime inconsistente.')
    for col in ['universe_total','universe_covered','breadth_eligible','leadership_eligible','breakout_event_count']:
        if not (d[col].notna()&d[col].ge(0)&d[col].mod(1).eq(0)).all(): raise ValueError('Contagem inválida.')
        d[col]=d[col].astype(int)
    if not d.universe_total.between(450,550).all(): raise ValueError('Universo fora dos limites.')
    if not d.universe_version.eq('current_sp500_'+d.universe_total.astype(str)+'_survivorship_bias').all():
        raise ValueError('Versão e tamanho do universo divergem.')
    if any(not d[col].le(d.universe_total).all() for col in ['universe_covered','breadth_eligible','leadership_eligible']):
        raise ValueError('Cobertura do universo inconsistente.')
    if not (d.distribution_count.isna()|d.distribution_count.between(0,20)).all():
        raise ValueError('Contagem de distribuição inválida.')
    return d.to_csv(index=False,lineterminator='\n').encode('utf-8')

def publish_snapshot(frame, filename, token, session=None):
    """Idempotent create-only publication; collisions never overwrite existing files."""
    if not re.fullmatch(r'market_health_daily_\d{8}T\d{6}Z\.csv',filename):
        raise ValueError('Nome de snapshot inválido.')
    payload=sanitized_csv(frame)
    if not isinstance(token,str) or not token.strip():
        raise ValueError('Configure MARKET_HEALTH_GITHUB_TOKEN nos Secrets do Colab.')
    client=session or requests.Session()
    headers={'Authorization':'Bearer '+token.strip(),'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    path='data/market_health/'+filename
    url='https://api.github.com/repos/'+REPOSITORY+'/contents/'+path
    def request(method, **kwargs):
        try:
            response=client.request(method,url,headers=headers,timeout=30,allow_redirects=False,**kwargs)
        except requests.RequestException:
            raise RuntimeError('Conexão com GitHub falhou. O CSV permanece no Drive.') from None
        return response
    def matches(response):
        try:
            obj=response.json()
            return obj.get('type')=='file' and base64.b64decode(obj['content'])==payload
        except (ValueError,KeyError,TypeError): return False
    found=request('GET',params={'ref':BRANCH})
    if found.status_code==200:
        if not matches(found): raise RuntimeError('Nome já existe com conteúdo diferente. Arquivo preservado.')
        status='already_present'
    elif found.status_code==404:
        written=request('PUT',json={'message':'Publish validated Market Health aggregate '+filename,'branch':BRANCH,'content':base64.b64encode(payload).decode('ascii')})
        if written.status_code not in (200,201,409,422):
            raise RuntimeError('GitHub recusou a publicação (HTTP '+str(written.status_code)+'). Verifique token e permissão Contents.')
        check=request('GET',params={'ref':BRANCH})
        if check.status_code!=200 or not matches(check):
            raise RuntimeError('Publicação sem confirmação; não sobrescreva. Confira o repositório e tente novamente.')
        status='published' if written.status_code in (200,201) else 'already_present'
    else:
        raise RuntimeError('GitHub recusou a consulta (HTTP '+str(found.status_code)+'). Verifique token e repositório.')
    return {'status':status,'rows':len(frame),'last_session':str(frame.date.iloc[-1]),'sha256':hashlib.sha256(payload).hexdigest(),'url':'https://github.com/'+REPOSITORY+'/blob/'+BRANCH+'/'+path}

def publish_from_colab(frame, daily_path):
    from google.colab import userdata
    try: token=userdata.get('MARKET_HEALTH_GITHUB_TOKEN')
    except Exception:
        raise RuntimeError('Adicione MARKET_HEALTH_GITHUB_TOKEN nos Secrets do Colab e habilite acesso para este notebook. Não cole o token em células.') from None
    try: return publish_snapshot(frame,Path(daily_path).name,token)
    finally: token=None

