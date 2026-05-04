from CacheService.cache import CacheService, DjangoCacheBackend
from api.permissions.permissions import get_permissions
from api.security.schema_authority import get_validated_schema
def get_pagebuilder(request, id=None, **kwargs):
    if id: 
        try:
            cache = CacheService()
            result = cache.get(id, "page_builder", get_validated_schema(kwargs))
            result = None
            if result is not None:
                return result
            page_data =  get_permissions(request, tableName='page_builder', id=id, **kwargs).get('data', [])                     
            filter = [{"field": "page_builder_id", "operator": "=", "value": id}]                             
            components_data =  get_permissions(request, tableName='page_component', where=filter, **kwargs)
            dashboard_components = []
            dashboard_details = []
            for component in components_data.get('data', []):
                if component.get('type') == 'dashboard':
                    dashboard_components.append(component.get('dashboard_component_id'))
            if dashboard_components:
                dashboard_details = get_permissions(
                    request,
                    tableName='dashboard_component',
                    where=[{'field': 'id', 'operator': 'in', 'value': dashboard_components}],
                    **kwargs
                ).get('data', [])                          
            sharedProfiles = get_permissions(request,tableName='page_builder_assignment', fields = ['profile_id', 'page_builder_id', 'profile.name', 'profile.profile_type'], where=[{'field':'page_builder_id', 'operator': '=', 'value': id}] ,**kwargs)   
            cache.set(id, {
                "page_builder": page_data[0],
                "components": components_data['data'],
                "shared_profiles": sharedProfiles,
                "dashboard_details": dashboard_details
            }, "page_builder", get_validated_schema(kwargs)) # Cache for 5 minutes                                      
            return {
                "page_builder": page_data[0],
                "components": components_data['data'],
                "shared_profiles": sharedProfiles,
                "dashboard_details": dashboard_details
            }                    
        except Exception as e:
            raise Exception(f"Error occurred: {e}")
    else:
        where = [{"field":"is_deleted",'value':False,"operator": "="}]
        results = get_permissions(request, tableName = 'page_builder',where=where, **kwargs).get('data', [])
        for result in results:
            sharedProfiles = get_permissions(request,tableName='page_builder_assignment', fields = ['id', 'profile_id', 'profile.name'], where=[{'field':'page_builder_id', 'operator': '=', 'value': result.get('id')}] ,**kwargs).get('data', [])
            result['total_profiles'] = len(sharedProfiles)
            result['profiles'] = sharedProfiles
        return results