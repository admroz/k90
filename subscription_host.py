"""Stable SIWC host initialization; migrate only an unbound legacy UUIDv4."""
import json
import os
import uuid

from subscription_auth import CredentialsError, TokenStore
from subscription_protocol import save_private


def initialize_host(directory):
    store=TokenStore(directory)
    with store._locked():
        path=store.directory/'registration.json'
        # Presence alone blocks identity changes: never open credentials here.
        # lexists also catches dangling symlinks and other unsafe filesystem entries.
        credentials_present = os.path.lexists(store.path)
        if path.is_symlink():
            raise CredentialsError('insecure_registration')
        if path.exists():
            try:
                record=json.loads(path.read_text())
            except (OSError,ValueError):
                raise CredentialsError('invalid_registration') from None
            if not isinstance(record,dict) or not isinstance(record.get('host_id'),str) or not record['host_id']:
                raise CredentialsError('invalid_registration')
            host_id = record['host_id']
            try:
                legacy = uuid.UUID(host_id)
            except ValueError:
                legacy = None
            # Only the exact UUIDv4 form emitted by the old generator is eligible.
            if legacy is None or legacy.version != 4 or str(legacy) != host_id:
                return record
            # The old, never-bound initializer wrote only this one field.
            # Unknown metadata is not evidence that migration is safe.
            if credentials_present or set(record) != {'host_id'}:
                raise CredentialsError('host_identity_bound')
            record = {**record, 'host_id': 'urn:uuid:' + host_id}
            save_private(path, record)
            return record
        if credentials_present:
            raise CredentialsError('host_identity_bound')
        record={'host_id':'urn:uuid:' + str(uuid.uuid4())}
        save_private(path,record)
        return record
