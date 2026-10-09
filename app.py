"""Standalone Market Health web dashboard; no direct access to private Google Drive."""
import os
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Market Health | v0.6',page_icon='📊',layout='wide')
st.title('Market Health — Painel independente')
st.caption('Versão web 0.6 • modelo quantitativo experimental, não indicador oficial de Mark Minervini')

NUMERIC=['score','coverage_pct','breadth50','breadth200','leadership_health','breakout_success_rate','breakout_event_count','distribution_count','trend_score','breadth_score','leadership_score','breakout_score','pressure_score']
FACTORS={'trend_score':('Tendência',25),'breadth_score':('Amplitude',20),'leadership_score':('Liderança',20),'breakout_score':('Rompimentos',20),'pressure_score':('Pressão vendedora',15)}

def normalize(frames):
    if not frames: raise ValueError('Nenhum arquivo CSV encontrado.')
    audit=pd.concat(frames,ignore_index=True)
    required={'date','coverage_pct','score','regime','universe_version'}
    if missing:=required.difference(audit.columns):raise ValueError('Campos ausentes: '+', '.join(sorted(missing)))
    audit['date']=pd.to_datetime(audit['date'],errors='coerce')
    audit['collected_at']=pd.to_datetime(audit.get('collected_at',pd.Series(index=audit.index,dtype='object')),errors='coerce',utc=True)
    for col in NUMERIC:
        if col not in audit: audit[col]=float('nan')
        audit[col]=pd.to_numeric(audit[col],errors='coerce')
    audit['universe_version']=audit['universe_version'].fillna('').astype(str)
    audit['family']=audit.universe_version.map(lambda x:'v0.3_sp500' if x.startswith('current_sp500_') and 'survivorship_bias' in x else 'legacy_or_unknown')
    audit['eligible']=audit.coverage_pct.eq(100)&audit.score.between(0,100)
    audit=audit.dropna(subset=['date']).copy()
    if audit.empty:raise ValueError('CSV não contém datas válidas.')
    return audit

def select_history(audit,family='v0.3_sp500'):
    sub=audit[audit.family.eq(family)].copy()
    if sub.empty:raise ValueError(f'Sem dados da família metodológica {family}.')
    sub=sub.sort_values(['date','eligible','coverage_pct','collected_at'],na_position='first')
    chosen=sub.drop_duplicates('date',keep='last').sort_values('date').reset_index(drop=True)
    chosen.loc[~chosen.eligible,'score']=float('nan')
    chosen.loc[~chosen.eligible,'regime']='NO_DATA'
    return chosen

def load_files(folder,uploads):
    if uploads:
        return [pd.read_csv(f) for f in uploads]
    files=sorted(folder.glob('market_health_daily_*.csv')) if folder.is_dir() else []
    return [pd.read_csv(f) for f in files]

st.sidebar.header('Fonte e período')
uploads=st.sidebar.file_uploader('Envie CSV(s) exportados pelo notebook v0.3',type='csv',accept_multiple_files=True)
local_folder=Path(os.getenv('MARKET_HEALTH_DIR','data/market_health'))
st.sidebar.caption('Sem upload: tenta ler arquivos CSV da pasta data/market_health da implantação. O Drive privado não é acessado automaticamente.')
try:
    audit=normalize(load_files(local_folder,uploads))
    history=select_history(audit)
except Exception as exc:
    st.info('Para visualizar o painel, envie o arquivo **market_health_daily_*.csv** exportado pelo Colab, ou configure uma pasta de snapshots na implantação.')
    st.caption(f'Detalhe: {exc}')
    st.stop()

period=st.sidebar.selectbox('Período',['Todos','20 pregões','60 pregões','120 pregões'],index=2)
limit={'Todos':None,'20 pregões':20,'60 pregões':60,'120 pregões':120}[period]
view=history.tail(limit) if limit else history
latest=view.iloc[-1]
valid=bool(latest.eligible)
score=f'{latest.score:.2f}/100' if valid else 'NO_DATA'
regime=str(latest.regime) if valid else 'NO_DATA'
cols=st.columns(4)
cols[0].metric('Market Health Score',score)
cols[1].metric('Regime',regime)
cols[2].metric('Cobertura',f'{latest.coverage_pct:.0f}%' if pd.notna(latest.coverage_pct) else 'NO_DATA')
cols[3].metric('Último pregão',latest.date.strftime('%d/%m/%Y'))
if not valid: st.warning('Score incompleto: o regime não pode ser determinado.')
if 'survivorship_bias' in latest.universe_version:st.info('Viés de sobrevivência: foram usados constituintes atuais do S&P 500. Esta série histórica não é backtest point-in-time.')
if 'warning_flags' in view and pd.notna(latest.get('warning_flags')) and str(latest.get('warning_flags')).strip():
    st.warning('Alertas do motor: '+str(latest.warning_flags).replace('|',' · '))

st.subheader('Evolução histórica do score')
st.line_chart(view.set_index('date')['score'],y_label='Score 0–100')
st.caption('Limiares heurísticos: defensivo abaixo de 45; neutro de 45 a menos de 70; favorável a partir de 70.')
st.subheader('Componentes do diagnóstico')
st.line_chart(view.set_index('date')[list(FACTORS)].rename(columns={k:v[0] for k,v in FACTORS.items()}),y_label='Pontos')
st.dataframe(pd.DataFrame([{'Componente':label,'Pontos':round(latest[k],2) if pd.notna(latest[k]) else None,'Máximo':maximum} for k,(label,maximum) in FACTORS.items()]),hide_index=True)
st.subheader('Amplitude e liderança')
st.line_chart(100*view.set_index('date')[['breadth50','breadth200','leadership_health']].rename(columns={'breadth50':'Acima MM50','breadth200':'Acima MM200','leadership_health':'Líderes saudáveis'}),y_label='%')
st.subheader('Rompimentos e pressão vendedora')
a,b,c=st.columns(3)
a.metric('Taxa de sucesso',f'{latest.breakout_success_rate:.1%}' if pd.notna(latest.breakout_success_rate) else 'NO_DATA')
b.metric('Eventos avaliados',str(int(latest.breakout_event_count)) if pd.notna(latest.breakout_event_count) else 'NO_DATA')
c.metric('Dias distribuição (média)',f'{latest.distribution_count:.1f}' if pd.notna(latest.distribution_count) else 'NO_DATA')
st.line_chart(100*view.set_index('date')['breakout_success_rate'],y_label='%')
st.line_chart(view.set_index('date')['distribution_count'],y_label='Dias')
st.subheader('Permanência nos regimes')
reg=view[['date','regime','score']].copy()
reg.loc[reg.score.isna(),'regime']='NO_DATA'
reg['segment']=reg.regime.ne(reg.regime.shift()).cumsum()
segments=reg.groupby('segment').agg(inicio=('date','min'),fim=('date','max'),regime=('regime','first'),pregoes=('regime','size')).reset_index(drop=True)
st.dataframe(segments.tail(12),hide_index=True)
if valid and latest.trend_score>=20 and pd.notna(latest.breadth50) and latest.breadth50<.4:
    st.warning('Divergência: tendência dos índices forte, mas menos de 40% da amostra acima da MM50.')
with st.expander('Auditoria e download'):
    st.caption(f'{len(audit)} registros originais; {len(history)} pregões únicos da família v0.3_sp500. Registros legados preservados apenas na auditoria.')
    st.dataframe(view.sort_values('date',ascending=False),hide_index=True)
    st.download_button('Baixar histórico filtrado',view.to_csv(index=False).encode('utf-8'),'market_health_web_export.csv','text/csv')
    st.dataframe(audit[['date','family','eligible','coverage_pct','score']].tail(30),hide_index=True)
