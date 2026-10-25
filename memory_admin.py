"""Explicit local memory maintenance. No implicit production-history import."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from k90_memory import rebuild_queue, upsert_source
from k90_memory.store import current
from k90_memory.privacy import strict_json_loads
import memory_runtime
from tools.db import get_conn, get_db_path


def _legacy_text(raw):
    try:
        parts=strict_json_loads(raw)
    except (ValueError,TypeError):
        return raw
    if isinstance(parts,list) and all(isinstance(p,dict) and p.get('type') in ('text','image_url') for p in parts):
        return memory_runtime._text(parts)
    return raw


def _timestamp(raw):
    try:
        value=datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value=value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    except (ValueError,TypeError):
        return 'unset'


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local memory status, explicit backfill/rebuild and one worker tick.')
    parser.add_argument('--owner',default=os.getenv('CONVERSATION_USER_ID','owner'))
    actions=parser.add_subparsers(dest='action',required=True)
    actions.add_parser('status')
    actions.add_parser('rebuild',help='Queue current local sources; does not purge unrelated remote content.')
    once=actions.add_parser('run-once',help='Explicit bounded real backend I/O if configured.')
    once.add_argument('--limit',type=int,default=3)
    backfill=actions.add_parser('backfill',help='Select one bounded legacy conversation batch; dry-run unless --apply.')
    backfill.add_argument('--after-id',type=int,default=0)
    backfill.add_argument('--limit',type=int,default=100)
    backfill.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    if not Path(get_db_path()).is_file():
        print(json.dumps({'error':'database_not_found'}))
        return 1
    try:
        if args.action=='run-once':
            claimed=memory_runtime.run_pending(limit=max(0,min(args.limit,100)))
            print(json.dumps({'claimed_jobs':claimed,'note':'claimed is not an acknowledgement count'}))
            return 0
        with closing(get_conn()) as conn,conn:
            if args.action=='backfill':
                rows=conn.execute('''SELECT id,role,content,timestamp FROM conversations
                    WHERE user_id=? AND id>? AND role IN ('user','assistant') ORDER BY id LIMIT ?''',
                    (args.owner,max(0,args.after_id),max(1,min(args.limit,1000)))).fetchall()
                imported=0
                if args.apply:
                    memory_runtime.initialize(conn)
                    for row in rows:
                        source_id='conversation:'+str(row['id'])
                        text=_legacy_text(row['content'])
                        local_only=memory_runtime._local_only(row['content'])
                        if not text:
                            continue
                        old=current(conn,args.owner,source_id)
                        if old and not old.deleted and old.content==text and old.local_only==local_only:
                            continue
                        upsert_source(conn,source_id,args.owner,row['role'],text,_timestamp(row['timestamp']),local_only=local_only)
                        imported+=1
                print(json.dumps({'selected_rows':len(rows),'last_selected_id':rows[-1]['id'] if rows else None,
                                  'applied':args.apply,'queued_sources':imported}))
            elif args.action=='rebuild':
                memory_runtime.initialize(conn)
                count=rebuild_queue(conn,args.owner)
                print(json.dumps({'queued_sources':count,'remote_purge_performed':False}))
            else:
                initialized=conn.execute("SELECT 1 FROM sqlite_master WHERE name='memory_sources'").fetchone() is not None
                if not initialized:
                    print(json.dumps({'memory_initialized':False}))
                    return 0
                count=conn.execute('SELECT count(*) FROM memory_sources WHERE owner=? AND deleted=0',(args.owner,)).fetchone()[0]
                outbox={r[0]:r[1] for r in conn.execute('SELECT status,count(*) FROM memory_outbox WHERE owner=? GROUP BY status',(args.owner,))}
                print(json.dumps({'memory_initialized':True,'active_sources':count,'outbox':outbox}))
        return 0
    except Exception:
        print(json.dumps({'error':'memory_admin_failed'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
