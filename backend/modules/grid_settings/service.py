import json

from modules.grid_settings import repository


def get_settings(user_id: str, grid_key: str):
    row = repository.get_settings(user_id, grid_key)
    if not row:
        return {'grid_key': grid_key, 'settings': None, 'updated_at': None}
    return {
        'grid_key': grid_key,
        'settings': json.loads(row['settings']),
        'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
    }


def save_settings(user_id: str, tenant_id: str | None, grid_key: str, settings: dict):
    repository.save_settings(user_id, tenant_id, grid_key, json.dumps(settings))
    return get_settings(user_id, grid_key)


def reset_settings(user_id: str, grid_key: str):
    repository.reset_settings(user_id, grid_key)
