import time
from os import environ

import jwt
from flask import abort, request
from hyp3_api import connexion_app


@connexion_app.app.before_request
def auth():
    token = request.cookies.get('asf-urs')
    if token:
        try:
            payload = jwt.decode(token, environ['AUTH_PUBLIC_KEY'], algorithms=environ['AUTH_ALGORITHM'])
            for group in payload['urs-groups']:
                if group['name'] == environ['AUTH_GROUP_NAME'] and group['app_uid'] == environ['AUTH_APP_UID']:
                    return
            abort(403)
        except (jwt.DecodeError, jwt.ExpiredSignatureError):
            pass


def decode_token(token, required_scopes):
    try:
        payload = jwt.decode(token, environ['AUTH_PUBLIC_KEY'], algorithms=environ['AUTH_ALGORITHM'])
        return {
            'active': True,
            'sub': payload['urs-user-id'],
        }
    except (jwt.ExpiredSignatureError, jwt.DecodeError):
        return None


def get_mock_jwt_cookie(user, lifetime_in_seconds=100, authorized=True):
    payload = {
        'urs-user-id': user,
        'exp': int(time.time()) + lifetime_in_seconds,
        'urs-groups': []
    }
    if authorized:
        payload['urs-groups'].append({
                'name': environ['AUTH_GROUP_NAME'],
                'app_uid':  environ['AUTH_APP_UID']
            })
    value = jwt.encode(
        payload=payload,
        key=environ['AUTH_PUBLIC_KEY'],
        algorithm=environ['AUTH_ALGORITHM'],
    )
    return value.decode()
