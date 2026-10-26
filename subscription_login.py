"""Operator CLI for k90-only ChatGPT OAuth and protected self-hosted transfer.

Run login on the browser's machine. Transfer credentials only over SSH; never chat.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import time

from subscription_auth import CredentialsError, TokenStore
from subscription_host import initialize_host
from subscription_protocol import authorize, request_json, revoke, save_private, validate_identity


def default_state_directory():
    return Path(os.getenv('K90_CHATGPT_STATE_DIR', str(Path(os.getenv('DATA_DIR', 'data'))/'chatgpt-auth')))


def login(directory, *, authorize_fn=None, confirm=None, request=None):
    directory=Path(directory)
    initialize_host(directory)
    tokens, client_id=(authorize_fn or authorize)(directory)
    try:
        if confirm is None or confirm() is not True:
            raise CredentialsError('cancelled')
        expires=tokens.get('expires_in')
        if not isinstance(expires,(int,float)) or isinstance(expires,bool) or not math.isfinite(expires) or expires<=0:
            raise CredentialsError('invalid_token_expiry')
        registration=json.loads((directory/'registration.json').read_text())
        record={key:tokens[key] for key in ('access_token','refresh_token','id_token','scope','token_type') if key in tokens}
        record.update({'client_id':client_id,'subject':registration['subject'],
                       'expires_at':time.time()+expires,'credits_setting_user_confirmed':True})
        # authorize() already verified this ID token's signature, identity and nonce.
        if tokens.get('id_token'):
            try:
                import jwt
                nonce=jwt.decode(tokens['id_token'],options={'verify_signature':False}).get('nonce')
                if isinstance(nonce,str):
                    record['nonce']=nonce
            except Exception:
                pass
        TokenStore(directory,request=request).install(record)
    except BaseException as exc:
        confirmed=False
        try:
            confirmed=revoke(tokens,client_id,request=request) is True
        except BaseException:
            pass
        setattr(exc,'renewable_session_revoked',confirmed)
        raise
    finally:
        tokens.clear()


def status(directory):
    store=TokenStore(directory)
    with store._locked():
        try:
            record=store._read()
        except CredentialsError as exc:
            if str(exc)=='login_required':
                return {'authenticated':False}
            raise
        return {'authenticated':True,'expires_at':record['expires_at'],
                'refresh_due':record['expires_at']<=time.time()+60,
                'credits_setting_user_confirmed':record.get('credits_setting_user_confirmed') is True}


def import_session(directory, source_directory, *, request=None, validator=None):
    """Explicit trusted SSH-transfer import, keeping the destination's host ID.

    The source session must not keep refreshing after transfer. ID identity is
    reverified; importing credentials is not an OAuth authorization callback.
    """
    directory,source_directory=Path(directory),Path(source_directory)
    if directory.resolve()==source_directory.resolve():
        raise CredentialsError('same_credential_directory')
    registration=initialize_host(directory)
    source=TokenStore(source_directory)
    with source._locked():
        record=source._read()
    nonce=record.get('nonce')
    if not isinstance(nonce,str) or not nonce or not record.get('id_token'):
        raise CredentialsError('fresh_login_required_for_import')
    fetch=request or request_json
    validate=validator or validate_identity
    jwks=fetch('https://auth.openai.com/.well-known/jwks.json')
    subject=validate(record,record['client_id'],nonce,jwks)
    if subject!=record['subject']:
        raise CredentialsError('account_mismatch')
    # Host metadata is never copied from the laptop, even if it is in the record.
    safe={key:record[key] for key in ('client_id','subject','access_token','refresh_token','id_token',
          'scope','token_type','expires_at','nonce','credits_setting_user_confirmed') if key in record}
    TokenStore(directory,request=request).install(safe)
    save_private(directory/'registration.json',{**registration,'client_id':record['client_id'],'subject':subject})


def main(argv=None):
    parser=argparse.ArgumentParser(description='Independent k90 ChatGPT authorization; no API-key fallback.')
    parser.add_argument('--state-dir',type=Path,default=None)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('login',help='Sign in on the machine opening the browser.')
    commands.add_parser('status',help='Local status without tokens, identity, or a network request.')
    commands.add_parser('logout',help='Revoke renewable session and remove local tokens.')
    commands.add_parser('init-host',help='Create this self-hosted runtime host identity before transfer.')
    importer=commands.add_parser('import-session',help='Import a protected SSH-transferred session directory.')
    importer.add_argument('source_directory',type=Path)
    args=parser.parse_args(argv)
    directory=args.state_dir or default_state_directory()
    try:
        if args.command=='login':
            def confirm():
                print('W ustawieniach użycia ChatGPT wyłącz dodatkowe kredyty dla aplikacji k90. Nie potrafimy sprawdzić tego przez API.')
                return input('Kredyty są wyłączone; zezwalam na używanie limitu subskrypcji [t/N]: ').strip().casefold()=='t'
            login(directory,confirm=confirm)
            print('Zapisano zweryfikowaną sesję k90 w prywatnym magazynie. Nie uruchomiono inference.')
        elif args.command=='status':
            print(json.dumps(status(directory),indent=2))
        elif args.command=='init-host':
            initialize_host(directory)
            print('Host initialized; no tokens or identity displayed.')
        elif args.command=='import-session':
            import_session(directory,args.source_directory)
            print('Imported after identity verification; destination host ID preserved. Stop using the source session.')
        elif args.command=='logout':
            confirmed=TokenStore(directory).logout()
            print(json.dumps({'local_tokens_cleared':True,'renewable_session_revoked':confirmed}))
            if not confirmed:
                print('UWAGA: odłącz aplikację k90 w ustawieniach ChatGPT; nie potwierdzono zdalnego unieważnienia.')
                return 1
        return 0
    except BaseException as exc:
        if isinstance(exc,SystemExit):
            raise
        code=str(exc) if isinstance(exc,CredentialsError) and re.fullmatch(r'[a-z0-9_]{1,100}',str(exc)) else 'authorization_failed'
        print(json.dumps({'error':code}))
        if getattr(exc,'renewable_session_revoked',None) is False:
            print('UWAGA: nie potwierdzono unieważnienia. Odłącz aplikację k90 w ustawieniach ChatGPT.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
