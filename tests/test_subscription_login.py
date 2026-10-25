"""Offline operator flows; no real credentials or browser login."""
import importlib
import json

import pytest


SCOPES='openid resource.invoke chatgpt.tokens.use.direct'


def test_login_stores_only_its_verified_registration_and_confirms_credit_setting(tmp_path):
    cli=importlib.import_module('subscription_login')
    def authorize(directory):
        cli.save_private(directory/'registration.json', {'host_id':'synthetic-host', 'client_id':'oaiapp_synthetic', 'subject':'synthetic-user'})
        return {'access_token':'synthetic-access','refresh_token':'synthetic-refresh','id_token':'synthetic-id',
                'scope':SCOPES,'token_type':'Bearer','expires_in':3600}, 'oaiapp_synthetic'
    cli.login(tmp_path/'auth',authorize_fn=authorize,confirm=lambda:True)
    saved=json.loads((tmp_path/'auth'/'credentials.json').read_text())
    assert saved['subject']=='synthetic-user'
    assert saved['credits_setting_user_confirmed'] is True
    assert cli.status(tmp_path/'auth')['authenticated'] is True


def test_cancel_after_oauth_revokes_without_persisting_tokens(tmp_path):
    cli=importlib.import_module('subscription_login')
    revocations=[]
    def authorize(directory):
        cli.save_private(directory/'registration.json', {'host_id':'synthetic-host','subject':'synthetic-user'})
        return {'access_token':'synthetic-access','refresh_token':'synthetic-refresh',
                'scope':SCOPES,'token_type':'Bearer','expires_in':3600}, 'oaiapp_synthetic'
    with pytest.raises(cli.CredentialsError,match='cancelled'):
        cli.login(tmp_path/'auth',authorize_fn=authorize,confirm=lambda:False,
                  request=lambda url,**kw:revocations.append((url,kw)) or {})
    assert len(revocations)==1
    assert not (tmp_path/'auth'/'credentials.json').exists()


def test_help_never_opens_login(capsys):
    cli=importlib.import_module('subscription_login')
    with pytest.raises(SystemExit) as result:
        cli.main(['--help'])
    assert result.value.code==0
    assert 'login' in capsys.readouterr().out


def test_initializing_vm_host_preserves_existing_host_identifier(tmp_path):
    cli=importlib.import_module('subscription_login')
    first=cli.initialize_host(tmp_path/'auth')
    second=cli.initialize_host(tmp_path/'auth')
    assert first['host_id']==second['host_id']
    assert (tmp_path/'auth'/'registration.json').stat().st_mode & 0o777==0o600


def test_import_preserves_destination_host_and_validates_identity(tmp_path):
    cli=importlib.import_module('subscription_login')
    src=tmp_path/'laptop';dst=tmp_path/'vm'
    store=cli.TokenStore(src,request=lambda *a,**k:{})
    store.install({'client_id':'oaiapp_synthetic','subject':'synthetic-user','access_token':'synthetic-access',
        'refresh_token':'synthetic-refresh','id_token':'synthetic-id','scope':SCOPES,
        'token_type':'Bearer','expires_at':9999999999,'nonce':'synthetic-nonce',
        'credits_setting_user_confirmed':True,'host_id':'do-not-copy-laptop-host'})
    vm=cli.initialize_host(dst)
    validated=[]
    def validate(tokens,client,nonce,jwks):
        validated.append(client)
        return 'synthetic-user'
    cli.import_session(dst,src,request=lambda *a,**k:{'keys':[]},validator=validate)
    assert validated==['oaiapp_synthetic']
    registration=json.loads((dst/'registration.json').read_text())
    assert registration['host_id']==vm['host_id']
    assert 'host_id' not in json.loads((dst/'credentials.json').read_text())
