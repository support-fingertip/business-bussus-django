
from api.permissions.permissions import get_permissions

def get_objects_for_report(request, **kwargs):
    filter = [{'field': 'allow_reports', 'operator': '=', 'value': True}, {'field': 'setup', 'operator': '=', 'value': False}]
    return get_permissions(request, tableName='object', fields=['name', 'label', 'icon', 'icon_color', 'plural_label','type'], where=filter, order_by=[{'field': 'name', 'direction': 'ASC'}], **kwargs).get('data', [])

def get_objects(request, **kwargs):
    filter = [{'field': 'setup', 'operator': '=', 'value': False}]
    return get_permissions(request, tableName='object', fields=['name', 'label', 'icon', 'icon_color', 'plural_label','type'], where=filter, order_by=[{'field': 'name', 'direction': 'ASC'}], **kwargs).get('data', [])