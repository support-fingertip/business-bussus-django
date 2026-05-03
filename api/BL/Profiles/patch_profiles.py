from CacheService.cache import CacheService
from api.permissions.permissions import patch_permission, post_permission
from api.security.schema_authority import get_validated_schema
from django.utils import timezone
def update_profiles(request, data, **kwargs):
    param3 = kwargs.get('param3', None)
    cache = CacheService()
    
    # Always update the profile record's last_modified_date
    profile_update = {
        'id': data.get('profile_id'),
        'last_modified_date': timezone.now(),
        'last_modified_by_id': request.user_.get('id')
    }
    profile = patch_permission(request, 'profile', update_data=profile_update, **kwargs)
    
    if param3:
        field_permissions = data.get('field_permissions', [])  
        for field in field_permissions:
            field.pop("fields", None)
        cache.invalidate_by_id(param3, "profiles", get_validated_schema(kwargs))
        cache.invalidate_by_id(param3, "field_permissions", get_validated_schema(kwargs))
        cache.invalidate_all_by_table("field_permissions", get_validated_schema(kwargs))
        cache.invalidate_all_by_table("fields", get_validated_schema(kwargs))
        return patch_permission(request, 'field_permissions', update_data=field_permissions, **kwargs)
    results = []
    object_permissions = data.get('object_permissions', None) 
    if object_permissions: 
        for obj in object_permissions:
            obj.pop("object", None)
        cache.invalidate_all_by_table('object_permissions', get_validated_schema(kwargs))
        cache.invalidate_all_by_table('objects', get_validated_schema(kwargs))
        object_result = patch_permission(request, 'object_permissions', update_data=object_permissions, **kwargs)
        results.append(object_result)
            
    tab_permissions = data.get('tab_permissions',None)  
    if tab_permissions:
        for obj in tab_permissions:
            obj.pop("object", None)
        cache.invalidate_all_by_table('tab_permissions', get_validated_schema(kwargs))
        cache.invalidate_all_by_table('objects', get_validated_schema(kwargs))
        cache.invalidate_all_by_table('tabs', get_validated_schema(kwargs))
        tab_results = patch_permission(request, 'tab_permissions', update_data=tab_permissions, **kwargs)
        results.append(tab_results)
    
    app_permissions = data.get('app_permissions', None)
    if app_permissions:
        cache.invalidate_all_by_table('app_permissions', get_validated_schema(kwargs))
        cache.invalidate_all_by_table('apps', get_validated_schema(kwargs))
        for app in app_permissions:
            app.pop("app")    
        app_results = patch_permission(request, "app_permissions", update_data=app_permissions, **kwargs)
        results.append(app_results)   
    homepage_assignment = data.get('homepage_assignment', None)
    if homepage_assignment:
        cache.invalidate_all_by_table('homepage_assignment', get_validated_schema(kwargs))
        cache.invalidate_all_by_table('page_builder', get_validated_schema(kwargs))
        if homepage_assignment.get('id'):
            # Existing record — UPDATE
            try:
                homepage_assignment.pop("profile")
                homepage_assignment.pop("page")
                homepage_assignment.pop("profile_id")
            except Exception:
                pass
            homepage_results = patch_permission(request, "homepage_assignment", update_data=[homepage_assignment], **kwargs)
        else:
            # No existing record — INSERT
            create_data = {
                'profile_id': homepage_assignment.get('profile_id'),
                'page_id': homepage_assignment.get('page_id'),
            }
            homepage_results = post_permission(request, "homepage_assignment", create_data=create_data, setup_check=False, **kwargs)
        results.append(homepage_results)
    return results