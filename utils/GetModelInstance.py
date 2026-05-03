from django.apps import apps


def getModel(object_name):
    try:
        Model = apps.get_model('custom_models', object_name)
    except LookupError:
        try:
            Model = apps.get_model('basicmodels', object_name)
        except LookupError:
            try:
                Model = apps.get_model('api', object_name)
            except LookupError:
                raise ValueError(f"Model '{object_name}' not found in 'objects' or 'basicmodels' apps.")
        
    return Model
    