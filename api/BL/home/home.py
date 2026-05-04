from CacheService.cache import CacheService
from api.BL.PageBuilder.get_pagebuilder import get_pagebuilder
from api.permissions.permissions import get_permissions
from api.security.schema_authority import get_validated_schema
def get_home_page(request, **kwargs):
    try:
        profile_id = kwargs.get('profile_id')
        cache = CacheService()
        d = cache.get(profile_id, "homepage_assignment", get_validated_schema(kwargs))
        d = None
        if d is None:           
            filter = [{"field": "profile_id", "operator": "equals", "value": profile_id}]
            d = get_permissions(request, tableName='homepage_assignment', where=filter, fields=['page_id'], **kwargs).get('data', [])
            if d:
                cache.set(profile_id, d, "homepage_assignment", get_validated_schema(kwargs))  # Cache for 5 minutes
        return get_pagebuilder(request, id = d[0].get('page_id', None) if len(d) > 0 else None,  **kwargs)  # Preload dashboards to utilize caching if implemented
    except Exception as e:
        raise Exception(f"Failed to fetch home page data: {e}")