import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

META_TOKEN     = os.getenv('META_ACCESS_TOKEN')
AD_ACCOUNT_ID  = os.getenv('META_AD_ACCOUNT_ID')
API_VERSION    = 'v19.0'
BASE_URL       = f'https://graph.facebook.com/{API_VERSION}'

DB_HOST = os.getenv('db_host', 'localhost').strip()
DB_NAME = os.getenv('db_database', 'pipeline').strip()
DB_USER = os.getenv('db_USER', 'developer').strip()
DB_PASS = os.getenv('db_PASSWORD').strip()
DB_PORT = '5432'

FIELDS = ','.join([
    'campaign_name', 'spend', 'impressions', 'clicks',
    'inline_link_clicks', 'cpm', 'ctr', 'cpc', 'reach', 'frequency',
    'date_start', 'date_stop',
])

def get_insights(date_start, date_stop):
    url = f'{BASE_URL}/{AD_ACCOUNT_ID}/insights'
    params = {
        'access_token': META_TOKEN,
        'fields': FIELDS,
        'time_range': f'{{"since":"{date_start}","until":"{date_stop}"}}',
        'time_increment': 1,
        'level': 'campaign',
        'limit': 500,
    }
    resultados = []
    while url:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        resultados.extend(data.get('data', []))
        paging = data.get('paging', {})
        url = paging.get('next')
        params = {}
        print(f'  Registros acumulados: {len(resultados)}')
    return resultados

def criar_tabela(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE SCHEMA IF NOT EXISTS meta;
            CREATE TABLE IF NOT EXISTS meta.meta_insights (
                id                  SERIAL PRIMARY KEY,
                campaign_name       TEXT,
                spend               NUMERIC,
                impressions         INTEGER,
                clicks              INTEGER,
                inline_link_clicks  INTEGER,
                cpm                 NUMERIC,
                ctr                 NUMERIC,
                cpc                 NUMERIC,
                reach               INTEGER,
                frequency           NUMERIC,
                date_start          DATE,
                date_stop           DATE,
                extracted_at        TIMESTAMP DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS meta_insights_unique
                ON meta.meta_insights (date_start, campaign_name);
        """)
    conn.commit()
    print('Tabela meta.meta_insights verificada/criada.')

def upsert_insights(conn, registros):
    if not registros:
        print('Nenhum registro pra inserir.')
        return
    rows = []
    for r in registros:
        rows.append((
            r.get('campaign_name'),
            float(r.get('spend', 0)),
            int(r.get('impressions', 0)),
            int(r.get('clicks', 0)),
            int(r.get('inline_link_clicks', 0)),
            float(r.get('cpm', 0)),
            float(r.get('ctr', 0)),
            float(r.get('cpc', 0)),
            int(r.get('reach', 0)),
            float(r.get('frequency', 0)),
            r.get('date_start'),
            r.get('date_stop'),
        ))
    sql = """
        INSERT INTO meta.meta_insights (
            campaign_name, spend, impressions, clicks,
            inline_link_clicks, cpm, ctr, cpc, reach, frequency,
            date_start, date_stop
        ) VALUES %s
        ON CONFLICT (date_start, campaign_name)
        DO UPDATE SET
            spend              = EXCLUDED.spend,
            impressions        = EXCLUDED.impressions,
            clicks             = EXCLUDED.clicks,
            inline_link_clicks = EXCLUDED.inline_link_clicks,
            cpm                = EXCLUDED.cpm,
            ctr                = EXCLUDED.ctr,
            cpc                = EXCLUDED.cpc,
            reach              = EXCLUDED.reach,
            frequency          = EXCLUDED.frequency,
            extracted_at       = NOW();
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    print(f'{len(rows)} registros inseridos/atualizados.')

if __name__ == '__main__':
    date_start = '2026-01-01'
    date_stop  = datetime.today().strftime('%Y-%m-%d')
    print(f'Extraindo Meta Ads de {date_start} ate {date_stop}...')
    registros = get_insights(date_start, date_stop)
    print(f'Total extraido: {len(registros)} registros')
    conn = psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS, port=DB_PORT
    )
    criar_tabela(conn)
    upsert_insights(conn, registros)
    conn.close()
    print('Pipeline Meta concluida.')
